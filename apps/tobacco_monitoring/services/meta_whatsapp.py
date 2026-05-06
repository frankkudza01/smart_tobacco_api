"""Meta WhatsApp Cloud API — outbound text messages for monitoring alerts."""

from __future__ import annotations

import logging
from typing import Any

from django.conf import settings

from apps.tobacco_monitoring.services.http_client import request_with_retries

logger = logging.getLogger(__name__)


class MetaWhatsAppError(Exception):
    pass


def send_text_message(*, to_e164: str, body: str) -> dict[str, Any]:
    """
    Send a WhatsApp text message via Cloud API.

    `to` must be digits only, no + prefix per Meta docs.
    """
    token = settings.META_WHATSAPP_ACCESS_TOKEN
    phone_id = settings.META_WHATSAPP_PHONE_NUMBER_ID
    if not token or not phone_id:
        raise MetaWhatsAppError("Meta WhatsApp is not configured (token or phone_number_id missing).")

    to_digits = "".join(c for c in to_e164 if c.isdigit())
    base = settings.META_WHATSAPP_BASE_URL.rstrip("/")
    url = f"{base}/{phone_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": to_digits,
        "type": "text",
        "text": {"preview_url": False, "body": body[:4096]},
    }
    resp = request_with_retries(
        "POST",
        url,
        json=payload,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        timeout=float(settings.META_WHATSAPP_TIMEOUT_SECONDS),
        max_retries=int(settings.META_WHATSAPP_MAX_RETRIES),
        log_label="meta_whatsapp",
    )
    data = resp.json() if resp.content else {}
    if resp.status_code >= 400:
        logger.warning("meta_whatsapp send failed status=%s body=%s", resp.status_code, str(data)[:500])
        raise MetaWhatsAppError(f"HTTP {resp.status_code}: {data}")
    logger.info("meta_whatsapp message sent to=%s", to_digits[-4:])
    return data
