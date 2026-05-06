"""
WaAPI (https://waapi.app) WhatsApp provider — Bearer token + instance actions.

Configure:
  WHATSAPP_PROVIDER=waapi
  WAAPI_TOKEN=<Bearer token from WaAPI dashboard (e.g. instance named TOBACCO)>
  WAAPI_INSTANCE_ID=<numeric instance id>
  WAAPI_BASE_URL=https://waapi.app/api/v1   (optional override)
  WAAPI_WEBHOOK_SECRET=<optional shared secret; require X-WAAPI-WEBHOOK-SECRET header>
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

import requests
from django.conf import settings
from django.http import HttpRequest

from apps.whatsapp.twilio_service import WhatsAppProvider

logger = logging.getLogger(__name__)


def _digits_only(phone: str) -> str:
    return re.sub(r"\D", "", phone or "")


def _to_waapi_chat_id(phone: str) -> str:
    """E.164 +263... or local digits -> chatId 263...@c.us"""
    d = _digits_only(phone)
    if d.startswith("0") and len(d) >= 9:
        d = "263" + d.lstrip("0")
    if not d.startswith("263") and len(d) == 9:
        d = "263" + d
    return f"{d}@c.us"


class WaapiWhatsAppProvider(WhatsAppProvider):
    """Outbound send + inbound JSON webhook parsing for WaAPI."""

    def __init__(self):
        self.base = (getattr(settings, "WAAPI_BASE_URL", "") or "https://waapi.app/api/v1").rstrip("/")
        self.instance_id = str(getattr(settings, "WAAPI_INSTANCE_ID", "") or "").strip()
        self.token = (getattr(settings, "WAAPI_TOKEN", "") or "").strip()
        self.webhook_secret = (getattr(settings, "WAAPI_WEBHOOK_SECRET", "") or "").strip()

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _action_url(self) -> str:
        return f"{self.base}/instances/{self.instance_id}/client/action/send-message"

    def _media_action_url(self) -> str:
        return f"{self.base}/instances/{self.instance_id}/client/action/send-media"

    def send_message(self, to: str, body: str) -> dict:
        chat_id = _to_waapi_chat_id(to)
        try:
            r = requests.post(
                self._action_url(),
                headers=self._headers(),
                json={"chatId": chat_id, "message": body},
                timeout=45,
            )
            sid = ""
            status = "queued"
            err = ""
            if r.status_code >= 400:
                status = "failed"
                err = r.text[:500] or f"HTTP {r.status_code}"
            else:
                try:
                    data = r.json()
                except json.JSONDecodeError:
                    data = {}
                sid = str(
                    data.get("data", {}).get("id")
                    or data.get("id")
                    or data.get("messageId")
                    or data.get("key", {}).get("id")
                    or f"waapi_{chat_id}",
                )
            logger.info("WaAPI send_message status=%s sid=%s to=%s", r.status_code, sid, chat_id)
            return {"sid": sid, "status": status, "error": err}
        except Exception as exc:
            logger.exception("WaAPI send_message failed to=%s", to)
            return {"sid": "", "status": "failed", "error": str(exc)}

    def send_media_message(self, to: str, body: str, media_url: str) -> dict:
        chat_id = _to_waapi_chat_id(to)
        try:
            r = requests.post(
                self._media_action_url(),
                headers=self._headers(),
                json={
                    "chatId": chat_id,
                    "mediaUrl": media_url,
                    "mediaCaption": body or " ",
                },
                timeout=90,
            )
            sid = ""
            status = "queued"
            err = ""
            if r.status_code >= 400:
                status = "failed"
                err = r.text[:500] or f"HTTP {r.status_code}"
            else:
                try:
                    data = r.json()
                except json.JSONDecodeError:
                    data = {}
                sid = str(data.get("data", {}).get("id") or data.get("id") or f"waapi_media_{chat_id}")
            return {"sid": sid, "status": status, "error": err}
        except Exception as exc:
            logger.exception("WaAPI send_media_message failed to=%s", to)
            return {"sid": "", "status": "failed", "error": str(exc)}

    def validate_webhook_signature(self, request: HttpRequest) -> bool:
        if not self.webhook_secret:
            return True
        got = request.headers.get("X-WAAPI-WEBHOOK-SECRET") or request.GET.get("waapi_secret", "")
        return got == self.webhook_secret

    def get_media_url(self, raw_payload: dict) -> str | None:
        return raw_payload.get("MediaUrl0") or None

    def webhook_expects_json(self) -> bool:
        return True

    def parse_inbound_to_twilio_shape(self, request: HttpRequest) -> dict[str, Any] | None:
        """
        Parse WaAPI JSON webhook into Twilio-compatible POST fields for the intent router.
        Returns None for events that should be ignored (no reply).
        """
        try:
            payload = request.data if hasattr(request, "data") else json.loads(request.body.decode("utf-8"))
        except Exception:
            try:
                payload = json.loads(request.body.decode("utf-8"))
            except Exception:
                return None

        if not isinstance(payload, dict):
            return None

        event = str(payload.get("event") or "").lower().replace(".", "_")
        if event not in ("message", "message_create"):
            return None

        data = payload.get("data") or {}
        msg = data.get("message")
        if not isinstance(msg, dict):
            msg = payload.get("message") if isinstance(payload.get("message"), dict) else {}
        if not isinstance(msg, dict):
            msg = data if isinstance(data, dict) and data.get("from") else {}

        if not msg:
            return None

        if msg.get("fromMe") is True:
            return None

        from_id = str(msg.get("from") or "")
        digits = from_id.split("@")[0] if "@" in from_id else _digits_only(from_id)
        if not digits:
            return None
        e164 = digits if digits.startswith("+") else f"+{digits}"
        if not e164.startswith("+"):
            e164 = f"+{e164}"

        body = str(msg.get("body") or msg.get("caption") or "").strip()
        mid = str(msg.get("id") or payload.get("id") or payload.get("timestamp") or "")

        out: dict[str, Any] = {
            "From": f"whatsapp:{e164}",
            "Body": body,
            "MessageSid": mid or f"waapi_{payload.get('timestamp', '')}",
        }

        has_media = bool(msg.get("hasMedia")) or str(msg.get("type", "")).lower() in (
            "image",
            "video",
            "document",
            "audio",
            "ptt",
        )
        media = msg.get("media") if isinstance(msg.get("media"), dict) else {}
        if has_media and isinstance(media, dict):
            url = media.get("url") or media.get("mediaUrl") or media.get("link")
            b64 = media.get("data")
            mime = media.get("mimetype") or media.get("mimeType") or "application/octet-stream"
            if url:
                out["NumMedia"] = "1"
                out["MediaUrl0"] = str(url)
                out["MediaContentType0"] = str(mime)
            elif b64:
                out["NumMedia"] = "1"
                out["MediaUrl0"] = f"data:{mime};base64,{str(b64).strip()}"
                out["MediaContentType0"] = str(mime)

        out["_provider"] = "waapi"
        out["_raw_waapi"] = payload
        return out
