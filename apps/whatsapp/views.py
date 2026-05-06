import logging
import time

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from apps.common.enums import WhatsAppDeliveryStatus, WhatsAppDirection
from apps.common.schema import EmptySchemaSerializer
from apps.common.utils import normalize_phone_number
from apps.whatsapp.intent_router import route_message
from apps.whatsapp.models import WhatsAppMessageLog
from apps.whatsapp.session_service import get_or_create_contact
from apps.whatsapp.tasks import send_whatsapp_message_task
from apps.whatsapp.twilio_service import get_whatsapp_provider

logger = logging.getLogger(__name__)


def _process_inbound_twilio_shape(
    *,
    raw_payload: dict,
    provider,
) -> HttpResponse:
    """Shared pipeline: rate limit, dedupe, log, route, queue outbound reply."""
    from_number_raw = raw_payload.get("From", "")
    body = raw_payload.get("Body", "").strip()
    provider_sid = raw_payload.get("MessageSid", "")

    phone = from_number_raw.replace("whatsapp:", "")
    normalized = normalize_phone_number(phone) or phone

    window = int(time.time() // 60)
    lim = getattr(settings, "WHATSAPP_WEBHOOK_RATE_LIMIT_PER_MINUTE", 60)
    rl_key = f"wa:rl:{normalized}:{window}"
    hits = cache.get(rl_key, 0)
    if hits >= lim:
        logger.warning("WhatsApp webhook rate limited phone=%s", normalized)
        return HttpResponse("Too Many Requests", status=429)
    cache.set(rl_key, hits + 1, timeout=120)

    if provider_sid:
        replay_key = f"wa:replay:{provider_sid}"
        if not cache.add(replay_key, 1, timeout=172800):
            logger.info("WhatsApp duplicate MessageSid=%s ignored", provider_sid)
            return _empty_webhook_response(provider)

    contact = get_or_create_contact(normalized)

    media_url = provider.get_media_url(raw_payload)
    media_type = raw_payload.get("MediaContentType0", "")

    msg_type = "media" if media_url else "text"
    WhatsAppMessageLog.objects.create(
        conversation=None,
        user=contact.user,
        phone_number=normalized,
        direction=WhatsAppDirection.INBOUND,
        message_type=msg_type,
        message_body=body,
        media_url=media_url or "",
        media_type=media_type,
        provider_message_id=provider_sid,
        delivery_status=WhatsAppDeliveryStatus.DELIVERED,
        raw_payload=raw_payload,
        processed_at=timezone.now(),
    )

    logger.info(
        "WhatsApp inbound: phone=%s body=%s media=%s",
        normalized,
        body[:100],
        bool(media_url),
    )

    reply = route_message(contact, body, media_url=media_url)

    send_whatsapp_message_task.delay(
        to=normalized,
        body=reply,
        user_id=str(contact.user.id) if contact.user else None,
    )

    return _empty_webhook_response(provider)


def _empty_webhook_response(provider):
    if getattr(provider, "webhook_expects_json", lambda: False)():
        return JsonResponse({"ok": True}, status=200)
    return HttpResponse(
        '<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
        content_type="text/xml",
        status=200,
    )


class WhatsAppWebhookView(APIView):
    """
    Inbound WhatsApp webhook.
    Twilio: application/x-www-form-urlencoded (default).
    WaAPI: application/json — normalized to the same pipeline as Twilio.
    """

    permission_classes = [AllowAny]
    authentication_classes = []
    serializer_class = EmptySchemaSerializer
    parser_classes = [JSONParser, FormParser, MultiPartParser]

    def post(self, request):
        provider = get_whatsapp_provider()
        if not provider.validate_webhook_signature(request):
            logger.warning("Invalid WhatsApp webhook signature")
            return HttpResponse("Forbidden", status=403)

        if getattr(provider, "webhook_expects_json", lambda: False)():
            parsed = getattr(provider, "parse_inbound_to_twilio_shape", lambda r: None)(request)
            if parsed is None:
                return JsonResponse({"ok": True}, status=200)
            raw_payload = parsed
        else:
            raw_payload = request.POST.dict()

        return _process_inbound_twilio_shape(raw_payload=raw_payload, provider=provider)


class WhatsAppDeliveryStatusView(APIView):
    """
    Delivery status callback from WhatsApp provider (Twilio form POST).
    WaAPI may POST JSON for ack events — best-effort update then 200.
    """

    permission_classes = [AllowAny]
    authentication_classes = []
    serializer_class = EmptySchemaSerializer
    parser_classes = [JSONParser, FormParser, MultiPartParser]

    def post(self, request):
        provider = get_whatsapp_provider()
        if not provider.validate_webhook_signature(request):
            return HttpResponse("Forbidden", status=403)

        if getattr(provider, "webhook_expects_json", lambda: False)():
            try:
                payload = request.data if isinstance(request.data, dict) else {}
            except Exception:
                payload = {}
            if isinstance(payload, dict):
                data = payload.get("data") or {}
                msg = data.get("message") if isinstance(data.get("message"), dict) else {}
                sid = str(
                    msg.get("id")
                    or payload.get("id")
                    or "",
                )
                ack = str(
                    msg.get("ack")
                    or data.get("ack")
                    or payload.get("ack")
                    or "",
                ).upper()
                status_map = {
                    "READ": WhatsAppDeliveryStatus.READ,
                    "DELIVERED": WhatsAppDeliveryStatus.DELIVERED,
                    "SENT": WhatsAppDeliveryStatus.SENT,
                }
                new_status = status_map.get(ack)
                if sid and new_status:
                    WhatsAppMessageLog.objects.filter(provider_message_id=sid).update(
                        delivery_status=new_status,
                        updated_at=timezone.now(),
                    )
            return HttpResponse("OK", status=200)

        sid = request.POST.get("MessageSid", "")
        status_str = request.POST.get("MessageStatus", "").upper()

        status_map = {
            "QUEUED": WhatsAppDeliveryStatus.QUEUED,
            "SENT": WhatsAppDeliveryStatus.SENT,
            "DELIVERED": WhatsAppDeliveryStatus.DELIVERED,
            "READ": WhatsAppDeliveryStatus.READ,
            "FAILED": WhatsAppDeliveryStatus.FAILED,
            "UNDELIVERED": WhatsAppDeliveryStatus.UNDELIVERED,
        }
        new_status = status_map.get(status_str)

        if sid and new_status:
            updated = WhatsAppMessageLog.objects.filter(
                provider_message_id=sid,
            ).update(
                delivery_status=new_status,
                updated_at=timezone.now(),
            )
            if updated:
                logger.info("Delivery status updated: sid=%s status=%s", sid, new_status)
            else:
                logger.warning("No message found for status update: sid=%s", sid)

        return HttpResponse("OK", status=200)
