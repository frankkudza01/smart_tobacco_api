"""
Farmer onboarding workflow — complete self-registration via WhatsApp.

States:
  INIT -> ASK_OTP -> VERIFY_OTP -> ASK_NAME -> ASK_NATIONAL_ID ->
  ASK_DISTRICT -> ASK_LANGUAGE -> CONFIRM -> DONE
"""
import logging

from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.accounts import otp_service
from apps.common.enums import UserRole
from apps.common.utils import normalize_phone_number
from apps.whatsapp.session_service import advance_state, end_conversation
from apps.whatsapp.workflows.base import BaseWorkflow, Reply

User = get_user_model()
logger = logging.getLogger(__name__)


class FarmerOnboardingWorkflow(BaseWorkflow):

    def get_name(self) -> str:
        return "farmer_onboarding"

    def handle_init(self, conv, body, contact):
        phone = contact.phone_number
        existing = User.objects.filter(phone_number=phone, is_active=True).first()
        if existing:
            end_conversation(conv)
            return Reply(
                f"You already have an account ({existing.full_name}). Type HELP for commands.",
                end_conversation=True,
            )

        code, err = otp_service.generate_otp(phone)
        if err:
            return Reply(err)

        from apps.whatsapp.tasks import send_otp_via_whatsapp_task
        send_otp_via_whatsapp_task.delay(phone=phone, otp_code=code)

        advance_state(conv, "VERIFY_OTP")
        return Reply(
            "Welcome! Let's get you registered as a tobacco farmer.\n\n"
            "We've sent a verification code to this number. "
            "Please enter the 6-digit code:"
        )

    def handle_verify_otp(self, conv, body, contact):
        code = body.strip()
        ok, err = otp_service.verify_otp(contact.phone_number, code)
        if not ok:
            return Reply(f"Verification failed: {err}\nPlease try again or type CANCEL.")

        contact.is_verified = True
        contact.save(update_fields=["is_verified", "updated_at"])
        advance_state(conv, "ASK_NAME")
        return Reply("Phone verified! Please enter your full name (First Last):")

    def handle_ask_name(self, conv, body, contact):
        name = body.strip()
        parts = name.split(maxsplit=1)
        if len(parts) < 2:
            return Reply("Please enter both your first and last name:")

        advance_state(conv, "ASK_NATIONAL_ID", {
            "first_name": parts[0].title(),
            "last_name": parts[1].title(),
        })
        return Reply(f"Thank you, {parts[0].title()}. Please enter your National ID number:")

    def handle_ask_national_id(self, conv, body, contact):
        nid = body.strip().upper()
        if len(nid) < 4:
            return Reply("That doesn't look valid. Please enter your National ID number:")

        from apps.accounts.models import FarmerProfile
        if FarmerProfile.objects.filter(national_id=nid).exists():
            return Reply(
                "This National ID is already registered. "
                "If this is your account, please contact support. Type CANCEL to exit."
            )

        advance_state(conv, "ASK_DISTRICT", {"national_id": nid})
        return Reply("Enter your district (e.g. Mvurwi, Karoi, Bindura):")

    def handle_ask_district(self, conv, body, contact):
        district = body.strip().title()
        if len(district) < 2:
            return Reply("Please enter a valid district name:")

        advance_state(conv, "ASK_LANGUAGE", {"district": district})
        return Reply(
            "What is your preferred language?\n"
            "1. English\n"
            "2. Shona\n"
            "3. Ndebele"
        )

    def handle_ask_language(self, conv, body, contact):
        choice = self._parse_choice(body, 3)
        lang_map = {1: "en", 2: "sn", 3: "nd"}
        lang = lang_map.get(choice)
        if not lang:
            return Reply("Please choose 1, 2, or 3:")

        advance_state(conv, "CONFIRM", {"language": lang})
        d = conv.state_data
        return Reply(
            "Please confirm your details:\n\n"
            f"Name: {d['first_name']} {d['last_name']}\n"
            f"National ID: {d['national_id']}\n"
            f"District: {d['district']}\n"
            f"Language: {lang}\n\n"
            "Reply YES to confirm or NO to cancel."
        )

    def handle_confirm(self, conv, body, contact):
        if body.strip().lower() not in ("yes", "y"):
            end_conversation(conv)
            return Reply("Registration cancelled. Type REGISTER to start again.", end_conversation=True)

        d = conv.state_data
        from django.db import transaction

        with transaction.atomic():
            user = User.objects.create_user(
                email=f"{contact.phone_number.replace('+', '')}@whatsapp.local",
                password=None,
                first_name=d["first_name"],
                last_name=d["last_name"],
                phone_number=contact.phone_number,
                role=UserRole.SMALLHOLDER_FARMER,
            )
            user.set_unusable_password()
            user.save()

            from apps.accounts.models import FarmerProfile
            FarmerProfile.objects.create(
                user=user,
                national_id=d["national_id"],
                district=d["district"],
            )

            contact.user = user
            contact.linked_role = UserRole.SMALLHOLDER_FARMER
            contact.preferred_language = d.get("language", "en")
            contact.display_name = user.full_name
            contact.consent_given = True
            contact.consent_given_at = timezone.now()
            contact.save()

        from apps.audit.services import log_audit
        log_audit(
            actor=user,
            action="WHATSAPP_FARMER_ONBOARDING",
            resource_type="User",
            resource_id=str(user.id),
            description=f"Farmer {user.full_name} self-registered via WhatsApp",
        )

        end_conversation(conv)
        return Reply(
            f"Welcome {d['first_name']}! Your account is set up.\n\n"
            "You can now:\n"
            "- REGISTER FARM — register your farm\n"
            "- MY SETTLEMENTS — check payments\n"
            "- HELP — see all commands",
            end_conversation=True,
        )
