import logging

from celery import shared_task
from django.conf import settings

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=15)
def send_whatsapp_message_task(self, to: str, body: str, user_id: str = None,
                               message_type: str = "text"):
    from django.contrib.auth import get_user_model
    from apps.whatsapp.twilio_service import send_whatsapp_message

    User = get_user_model()
    user = None
    if user_id:
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            pass

    try:
        log = send_whatsapp_message(to=to, body=body, user=user, message_type=message_type)
        if log.delivery_status == "FAILED":
            raise Exception(log.error_message)
        logger.info("WhatsApp task completed: sid=%s to=%s", log.provider_message_id, to)
    except Exception as exc:
        logger.exception("WhatsApp task failed: to=%s", to)
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=10)
def send_otp_via_whatsapp_task(self, phone: str, otp_code: str, user_id: str = None):
    from apps.whatsapp.twilio_service import send_whatsapp_message
    from django.contrib.auth import get_user_model

    User = get_user_model()
    user = None
    if user_id:
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            pass

    body = (
        f"Your Zimbabwe Tobacco Platform verification code is: {otp_code}\n\n"
        f"This code expires in {settings.OTP_TTL_SECONDS // 60} minutes. "
        f"Do not share this code with anyone."
    )

    if settings.ENABLE_DEV_OTP_LOGGING:
        logger.warning(
            "[DEV OTP DELIVERY] phone=%s code=%s  *** NON-PRODUCTION ONLY ***",
            phone, otp_code,
        )

    try:
        log = send_whatsapp_message(to=phone, body=body, user=user, message_type="otp")
        if log.delivery_status == "FAILED":
            raise Exception(log.error_message)
    except Exception as exc:
        logger.exception("OTP WhatsApp delivery failed: phone=%s", phone)
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=20)
def process_whatsapp_media_task(
    self,
    media_url: str,
    media_type: str,
    user_id: str,
    doc_type: str = "OTHER",
    lot_id: str = None,
    phone: str = "",
):
    """Download media from WhatsApp, store as Document, queue blockchain anchor."""
    from apps.whatsapp.media_service import (
        fetch_media_from_twilio,
        store_whatsapp_document,
        validate_media,
    )

    try:
        file_bytes, content_type = fetch_media_from_twilio(media_url)

        error = validate_media(file_bytes, content_type)
        if error:
            logger.warning("WhatsApp media validation failed: %s (phone=%s)", error, phone)
            if phone:
                send_whatsapp_message_task.delay(
                    to=phone, body=f"Document upload failed: {error}",
                )
            return

        doc = store_whatsapp_document(
            file_bytes=file_bytes,
            content_type=content_type,
            user_id=user_id,
            doc_type=doc_type,
            lot_id=lot_id,
        )

        from apps.blockchain.tasks import anchor_document_hash
        anchor_document_hash.delay(str(doc.id))

        logger.info("WhatsApp media processed: doc=%s hash=%s", doc.id, doc.sha256_hash[:16])

        if phone:
            send_whatsapp_message_task.delay(
                to=phone,
                body=(
                    f"Document received and stored!\n"
                    f"Type: {doc_type}\n"
                    f"Hash: {doc.sha256_hash[:16]}...\n"
                    f"Blockchain anchoring queued."
                ),
                user_id=user_id,
            )

    except Exception as exc:
        logger.exception("WhatsApp media processing failed: url=%s", media_url)
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=2, default_retry_delay=30)
def send_template_notification_task(
    self,
    phone: str,
    template_name: str,
    body: str,
    user_id: str = None,
    related_object_type: str = "",
    related_object_id: str = "",
):
    """Send a template-based notification and log it."""
    from apps.whatsapp.twilio_service import send_whatsapp_message
    from apps.whatsapp.models import WhatsAppContact, WhatsAppTemplateLog
    from django.contrib.auth import get_user_model

    User = get_user_model()
    user = None
    if user_id:
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            pass

    try:
        log = send_whatsapp_message(to=phone, body=body, user=user, message_type="template")

        contact = WhatsAppContact.objects.filter(phone_number=phone).first()
        WhatsAppTemplateLog.objects.create(
            template_name=template_name,
            contact=contact,
            related_object_type=related_object_type,
            related_object_id=related_object_id if related_object_id else None,
            send_status=log.delivery_status,
            provider_response={"sid": log.provider_message_id},
        )
    except Exception as exc:
        logger.exception("Template notification failed: phone=%s template=%s", phone, template_name)
        raise self.retry(exc=exc)


@shared_task
def send_bulk_reminder_task(reminder_type: str):
    """Scheduled task to send reminders (e.g. pending submissions, incomplete profiles)."""
    from django.contrib.auth import get_user_model
    from apps.common.enums import UserRole

    User = get_user_model()

    if reminder_type == "incomplete_profile":
        from apps.accounts.models import FarmerProfile
        farmers = User.objects.filter(
            role=UserRole.SMALLHOLDER_FARMER,
            is_active=True,
        ).exclude(phone_number="")

        for farmer in farmers:
            if not FarmerProfile.objects.filter(user=farmer).exists():
                send_whatsapp_message_task.delay(
                    to=farmer.phone_number,
                    body=(
                        "Reminder: Please complete your farmer profile on the "
                        "Zimbabwe Tobacco Platform. Type HELP to get started."
                    ),
                    user_id=str(farmer.id),
                )

    elif reminder_type == "pending_settlements":
        from apps.settlements.models import Settlement
        from apps.common.enums import SettlementStatus

        pending = Settlement.objects.filter(
            status=SettlementStatus.PENDING,
        ).select_related("farmer", "sale", "sale__lot")

        for settlement in pending:
            if settlement.farmer and settlement.farmer.phone_number:
                send_whatsapp_message_task.delay(
                    to=settlement.farmer.phone_number,
                    body=(
                        f"You have a pending settlement for lot {settlement.sale.lot.lot_number}: "
                        f"${settlement.amount_due}. Type MY SETTLEMENTS for details."
                    ),
                    user_id=str(settlement.farmer.id),
                )
