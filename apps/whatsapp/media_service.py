"""
Service for downloading, validating, hashing, and storing media from WhatsApp messages.
Fetches media from the provider (Twilio/Meta), stores in S3/MinIO,
creates a Document record, and queues blockchain anchoring.
"""
import base64
import io
import logging
import mimetypes
import uuid

import requests
from django.conf import settings
from django.core.files.base import ContentFile

from apps.common.enums import BlockchainAnchorStatus, DocumentType
from apps.common.utils import compute_sha256

logger = logging.getLogger(__name__)

ALLOWED_MEDIA_TYPES = {
    "image/jpeg", "image/png", "image/webp",
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

MAX_MEDIA_SIZE_BYTES = settings.MAX_DOCUMENT_SIZE_MB * 1024 * 1024


def fetch_media_from_source(media_url: str) -> tuple[bytes, str]:
    """
    Download media: Twilio-authenticated HTTPS URL, plain URL, or data URI (WaAPI base64).
    Returns (file_bytes, content_type).
    """
    if media_url.startswith("data:"):
        try:
            header, b64 = media_url.split(",", 1)
        except ValueError as exc:
            raise ValueError("Invalid data URI") from exc
        mime = "application/octet-stream"
        if ";" in header:
            mime = header[5:].split(";")[0].strip() or mime
        raw = base64.b64decode(b64.strip())
        return raw, mime

    auth = None
    if "twilio.com" in media_url and settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN:
        auth = (settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)

    resp = requests.get(media_url, auth=auth, timeout=60)
    resp.raise_for_status()

    content_type = resp.headers.get("Content-Type", "application/octet-stream").split(";")[0]
    return resp.content, content_type


def fetch_media_from_twilio(media_url: str) -> tuple[bytes, str]:
    """Backward-compatible name for callers."""
    return fetch_media_from_source(media_url)


def validate_media(file_bytes: bytes, content_type: str) -> str | None:
    """Validate media type and size. Returns error string or None."""
    if content_type not in ALLOWED_MEDIA_TYPES:
        return f"Unsupported file type: {content_type}"
    if len(file_bytes) > MAX_MEDIA_SIZE_BYTES:
        mb = len(file_bytes) / (1024 * 1024)
        return f"File too large: {mb:.1f}MB (max {settings.MAX_DOCUMENT_SIZE_MB}MB)"
    return None


def store_whatsapp_document(
    *,
    file_bytes: bytes,
    content_type: str,
    user_id: str,
    doc_type: str = DocumentType.OTHER,
    lot_id: str | None = None,
    title: str = "",
) -> "Document":
    """
    Store downloaded WhatsApp media as a Document record.
    Computes hash, stores file, returns the Document instance.
    """
    from apps.documents.models import Document

    ext = mimetypes.guess_extension(content_type) or ".bin"
    filename = f"whatsapp_{uuid.uuid4().hex[:12]}{ext}"

    file_obj = io.BytesIO(file_bytes)
    sha_hash = compute_sha256(file_obj)
    file_obj.seek(0)

    if not title:
        title = f"WhatsApp {doc_type} upload"

    doc = Document(
        uploaded_by_id=user_id,
        document_type=doc_type,
        title=title,
        file_name=filename,
        mime_type=content_type,
        file_size=len(file_bytes),
        sha256_hash=sha_hash,
        anchor_status=BlockchainAnchorStatus.PENDING,
    )
    if lot_id:
        doc.lot_id = lot_id

    doc.file.save(filename, ContentFile(file_bytes), save=False)
    doc.save()

    return doc
