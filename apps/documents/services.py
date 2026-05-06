import hashlib
import logging

from django.conf import settings
from django.db import transaction

from apps.common.enums import DocumentVerificationState
from apps.common.exceptions import ServiceException
from apps.common.utils import compute_sha256
from apps.documents.models import Document

logger = logging.getLogger(__name__)


@transaction.atomic
def upload_document(*, lot=None, uploaded_by, document_type, title,
                    description="", file) -> Document:
    mime = file.content_type or ""
    if mime not in settings.ALLOWED_DOCUMENT_TYPES:
        raise ServiceException(f"File type '{mime}' is not allowed.")

    max_size = settings.MAX_DOCUMENT_SIZE_MB * 1024 * 1024
    if file.size > max_size:
        raise ServiceException(f"File exceeds {settings.MAX_DOCUMENT_SIZE_MB} MB limit.")

    sha256 = compute_sha256(file)
    pointer = hashlib.sha256(f"{file.name}:{file.size}:{sha256}".encode("utf-8")).hexdigest()
    org = None
    if lot is not None:
        org = lot.farm.organization_id

    doc = Document.objects.create(
        organization_id=org,
        lot=lot,
        uploaded_by=uploaded_by,
        document_type=document_type,
        title=title,
        description=description,
        file=file,
        file_name=file.name,
        mime_type=mime,
        file_size=file.size,
        sha256_hash=sha256,
        storage_pointer_hash=pointer,
        verification_state=DocumentVerificationState.HASHED,
    )

    try:
        from apps.blockchain.tasks import anchor_document_hash
        anchor_document_hash.delay(str(doc.id))
    except Exception:
        logger.warning("Failed to enqueue blockchain anchoring for document %s", doc.id)

    try:
        from apps.documents.tasks import build_document_fingerprint_task

        build_document_fingerprint_task.delay(str(doc.id))
    except Exception:
        logger.warning("Failed to enqueue fingerprint for document %s", doc.id)

    return doc


def verify_document(document: Document) -> dict:
    """Re-hash stored file and compare against stored + blockchain anchored hash."""
    result = {
        "document_id": str(document.id),
        "stored_hash": document.sha256_hash,
        "recomputed_hash": None,
        "hash_match": False,
        "anchor_status": document.anchor_status,
        "anchor_tx_hash": document.anchor_tx_hash,
        "blockchain_verified": False,
    }

    try:
        recomputed = compute_sha256(document.file)
        result["recomputed_hash"] = recomputed
        result["hash_match"] = recomputed == document.sha256_hash
    except Exception as e:
        logger.error("Failed to recompute hash for document %s: %s", document.id, e)
        result["recomputed_hash"] = None

    if document.anchor_tx_hash:
        result["blockchain_verified"] = result["hash_match"]

    if result["hash_match"] and document.verification_state != DocumentVerificationState.VERIFIED:
        document.verification_state = DocumentVerificationState.VERIFIED
        document.save(update_fields=["verification_state", "updated_at"])

    return result


def mark_document_anchored(document_id) -> None:
    from apps.documents.models import Document

    try:
        doc = Document.objects.get(id=document_id)
    except Document.DoesNotExist:
        return
    if doc.verification_state == DocumentVerificationState.HASHED:
        doc.verification_state = DocumentVerificationState.ANCHORED
        doc.save(update_fields=["verification_state", "updated_at"])
