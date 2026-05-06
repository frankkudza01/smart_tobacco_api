"""Short-lived signed tokens for anomaly case packet export (auditor/admin)."""

from __future__ import annotations

from uuid import UUID

from django.core.signing import BadSignature, SignatureExpired, TimestampSigner
from django.urls import reverse

SALT = "ai-anomaly-export-v1"
MAX_AGE_SECONDS = 900


def sign_export_payload(*, alert_id: UUID, user_id) -> str:
    signer = TimestampSigner(salt=SALT)
    # Use "|" — UUID strings use "-", not ":" (":" conflicts with signer internals).
    return signer.sign(f"{alert_id}|{user_id}")


def unsign_export_token(token: str) -> tuple[UUID, str] | None:
    signer = TimestampSigner(salt=SALT)
    try:
        raw = signer.unsign(token, max_age=MAX_AGE_SECONDS)
    except (BadSignature, SignatureExpired):
        return None
    parts = raw.split("|", 1)
    if len(parts) != 2:
        return None
    try:
        return UUID(parts[0]), parts[1]
    except ValueError:
        return None


def build_export_download_url(request, token: str) -> str:
    path = reverse("ai-anomaly-export-download")
    return request.build_absolute_uri(f"{path}?t={token}")


def build_export_download_url_public(base_url: str, token: str) -> str:
    """Build absolute export URL when no HTTP request is available (e.g. WhatsApp)."""
    path = reverse("ai-anomaly-export-download")
    base = base_url.rstrip("/")
    return f"{base}{path}?t={token}"
