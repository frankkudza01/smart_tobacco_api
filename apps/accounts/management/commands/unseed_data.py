"""
Reverse `seed_data`: remove seeded users, organizations, and closely related rows.

Usage:
  python manage.py unseed_data
  python manage.py unseed_data --dry-run
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.accounts.models import OTPChallengeLog
from apps.accounts.seed_constants import (
    SEED_ORGANIZATION_REGISTRATION_NUMBERS,
    SEED_PHONE_NUMBERS,
    SEED_USER_EMAILS,
)
from apps.organizations.models import Organization
from apps.whatsapp.models import WhatsAppContact

User = get_user_model()


class Command(BaseCommand):
    help = "Remove database rows created by seed_data (see apps.accounts.seed_constants)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be deleted without changing the database",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        users = User.objects.filter(email__in=SEED_USER_EMAILS)
        orgs = Organization.objects.filter(registration_number__in=SEED_ORGANIZATION_REGISTRATION_NUMBERS)

        u_count = users.count()
        o_count = orgs.count()
        wc_count = WhatsAppContact.objects.filter(phone_number__in=SEED_PHONE_NUMBERS).count()
        otp_count = OTPChallengeLog.objects.filter(phone_number__in=SEED_PHONE_NUMBERS).count()

        self.stdout.write(
            f"Seed users (emails): {u_count}\n"
            f"Seed organizations (registration #): {o_count}\n"
            f"WhatsApp contacts (seed phones): {wc_count}\n"
            f"OTP challenge logs (seed phones): {otp_count}"
        )

        if u_count == 0 and o_count == 0 and wc_count == 0 and otp_count == 0:
            self.stdout.write(self.style.WARNING("Nothing to remove (no matching seed records)."))
            return

        if dry_run:
            self.stdout.write(self.style.WARNING("Dry run — no changes made."))
            return

        user_ids = list(users.values_list("pk", flat=True))

        with transaction.atomic():
            if user_ids:
                from apps.ai_assistant.models import AIInteractionLog
                from apps.audit.models import AuditLog
                from apps.provenance.models import ProvenanceQueryLog

                AIInteractionLog.objects.filter(actor_id__in=user_ids).delete()
                AuditLog.objects.filter(actor_id__in=user_ids).delete()
                ProvenanceQueryLog.objects.filter(queried_by_id__in=user_ids).delete()

            OTPChallengeLog.objects.filter(phone_number__in=SEED_PHONE_NUMBERS).delete()
            WhatsAppContact.objects.filter(phone_number__in=SEED_PHONE_NUMBERS).delete()

            deleted_users, _ = users.delete()
            deleted_orgs, _ = orgs.delete()

        self.stdout.write(
            self.style.SUCCESS(
                f"Removed seed data (users delete cascade: {deleted_users} rows affected; "
                f"organizations: {deleted_orgs})."
            )
        )
        self.stdout.write(
            "Note: BlockchainReceipt rows pointing at deleted trace events are not removed; "
            "delete those manually in admin if needed."
        )
