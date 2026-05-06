"""
WhatsApp provider abstraction layer.
Supports Twilio WhatsApp and Mock gateway for dev/tests.
Designed for easy extension to Meta WhatsApp Cloud API.
"""
import abc
import logging

from django.conf import settings

from apps.common.enums import WhatsAppDeliveryStatus, WhatsAppDirection
from apps.common.utils import format_whatsapp_number
from apps.whatsapp.models import WhatsAppMessageLog

logger = logging.getLogger(__name__)


class WhatsAppProvider(abc.ABC):
    """Abstract provider — can be Twilio, Meta, WaAPI, or mock."""

    def webhook_expects_json(self) -> bool:
        """True if inbound webhook is JSON (e.g. WaAPI) instead of Twilio form POST."""
        return False

    @abc.abstractmethod
    def send_message(self, to: str, body: str) -> dict:
        """Send a WhatsApp message. Returns {"sid": ..., "status": ...}."""

    @abc.abstractmethod
    def send_media_message(self, to: str, body: str, media_url: str) -> dict:
        """Send a WhatsApp message with media attachment."""

    @abc.abstractmethod
    def validate_webhook_signature(self, request) -> bool:
        """Validate inbound webhook signature from the provider."""

    @abc.abstractmethod
    def get_media_url(self, raw_payload: dict) -> str | None:
        """Extract downloadable media URL from inbound webhook payload."""


class TwilioWhatsAppProvider(WhatsAppProvider):

    def __init__(self):
        from twilio.rest import Client
        self.client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        self.from_number = settings.TWILIO_WHATSAPP_FROM

    def send_message(self, to: str, body: str) -> dict:
        to_wa = format_whatsapp_number(to)
        try:
            message = self.client.messages.create(
                body=body,
                from_=self.from_number,
                to=to_wa,
            )
            logger.info("Twilio WhatsApp sent: sid=%s to=%s", message.sid, to_wa)
            return {"sid": message.sid, "status": message.status or "queued"}
        except Exception as exc:
            logger.exception("Twilio WhatsApp send failed to=%s", to_wa)
            return {"sid": "", "status": "failed", "error": str(exc)}

    def send_media_message(self, to: str, body: str, media_url: str) -> dict:
        to_wa = format_whatsapp_number(to)
        try:
            message = self.client.messages.create(
                body=body,
                from_=self.from_number,
                to=to_wa,
                media_url=[media_url],
            )
            return {"sid": message.sid, "status": message.status or "queued"}
        except Exception as exc:
            logger.exception("Twilio WhatsApp media send failed to=%s", to_wa)
            return {"sid": "", "status": "failed", "error": str(exc)}

    def validate_webhook_signature(self, request) -> bool:
        from twilio.request_validator import RequestValidator
        validator = RequestValidator(settings.TWILIO_AUTH_TOKEN)
        scheme = request.headers.get("X-Forwarded-Proto", request.scheme)
        url = f"{scheme}://{request.get_host()}{request.path}"
        post_vars = request.POST.dict()
        signature = request.META.get("HTTP_X_TWILIO_SIGNATURE", "")
        return validator.validate(url, post_vars, signature)

    def get_media_url(self, raw_payload: dict) -> str | None:
        num_media = int(raw_payload.get("NumMedia", "0"))
        if num_media > 0:
            return raw_payload.get("MediaUrl0")
        return None


class MetaWhatsAppProvider(WhatsAppProvider):
    """
    Placeholder for Meta WhatsApp Cloud API.
    Implement when switching from Twilio to direct Meta integration.
    """

    def send_message(self, to: str, body: str) -> dict:
        raise NotImplementedError("Meta provider not yet implemented")

    def send_media_message(self, to: str, body: str, media_url: str) -> dict:
        raise NotImplementedError("Meta provider not yet implemented")

    def validate_webhook_signature(self, request) -> bool:
        raise NotImplementedError("Meta provider not yet implemented")

    def get_media_url(self, raw_payload: dict) -> str | None:
        raise NotImplementedError("Meta provider not yet implemented")


class MockWhatsAppProvider(WhatsAppProvider):
    """For local development and tests — logs instead of sending."""

    sent_messages: list = []

    def __init__(self):
        self.sent_messages = []

    def send_message(self, to: str, body: str) -> dict:
        logger.info("[MOCK WhatsApp] to=%s body=%s", to, body[:200])
        self.sent_messages.append({"to": to, "body": body})
        return {"sid": f"MOCK_{to}", "status": "sent"}

    def send_media_message(self, to: str, body: str, media_url: str) -> dict:
        logger.info("[MOCK WhatsApp] media to=%s body=%s url=%s", to, body[:100], media_url)
        self.sent_messages.append({"to": to, "body": body, "media_url": media_url})
        return {"sid": f"MOCK_MEDIA_{to}", "status": "sent"}

    def validate_webhook_signature(self, request) -> bool:
        return True

    def get_media_url(self, raw_payload: dict) -> str | None:
        num_media = int(raw_payload.get("NumMedia", "0"))
        if num_media > 0:
            return raw_payload.get("MediaUrl0")
        return None


def get_whatsapp_provider() -> WhatsAppProvider:
    """
    Provider selection order (WHATSAPP_PROVIDER env):
      - waapi: WaAPI when WAAPI_TOKEN + WAAPI_INSTANCE_ID set, else mock
      - twilio: Twilio when SID+token set, else mock
      - mock: always mock
      - auto: WaAPI if configured, else Twilio if configured, else mock
    """
    mode = (getattr(settings, "WHATSAPP_PROVIDER", "auto") or "auto").lower()
    waapi_ok = bool(getattr(settings, "WAAPI_TOKEN", "")) and bool(
        str(getattr(settings, "WAAPI_INSTANCE_ID", "")).strip()
    )
    twilio_ok = bool(settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN)

    if mode == "mock":
        return MockWhatsAppProvider()
    if mode == "waapi":
        if waapi_ok:
            from apps.whatsapp.waapi_provider import WaapiWhatsAppProvider

            return WaapiWhatsAppProvider()
        logger.warning("WHATSAPP_PROVIDER=waapi but WAAPI_TOKEN or WAAPI_INSTANCE_ID missing; using mock")
        return MockWhatsAppProvider()
    if mode == "twilio":
        if twilio_ok:
            return TwilioWhatsAppProvider()
        logger.warning("WHATSAPP_PROVIDER=twilio but Twilio credentials missing; using mock")
        return MockWhatsAppProvider()
    # auto
    if waapi_ok:
        from apps.whatsapp.waapi_provider import WaapiWhatsAppProvider

        return WaapiWhatsAppProvider()
    if twilio_ok:
        return TwilioWhatsAppProvider()
    return MockWhatsAppProvider()


def send_whatsapp_message(
    *, to: str, body: str, user=None, message_type: str = "text",
    conversation=None,
) -> WhatsAppMessageLog:
    """High-level send function: dispatches via provider and logs the message."""
    provider = get_whatsapp_provider()
    result = provider.send_message(to, body)

    log = WhatsAppMessageLog.objects.create(
        conversation=conversation,
        user=user,
        phone_number=to,
        direction=WhatsAppDirection.OUTBOUND,
        message_type=message_type,
        message_body=body,
        provider_message_id=result.get("sid", ""),
        delivery_status=(
            WhatsAppDeliveryStatus.FAILED if result.get("status") == "failed"
            else WhatsAppDeliveryStatus.QUEUED
        ),
        error_message=result.get("error", ""),
    )
    return log
