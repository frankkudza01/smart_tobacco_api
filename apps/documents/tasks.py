import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name="documents.build_document_fingerprint")
def build_document_fingerprint_task(document_id: str):
    from apps.documents.models import Document
    from apps.documents.fingerprint_service import build_or_update_fingerprint, scan_near_duplicates_for_document

    try:
        doc = Document.objects.get(id=document_id)
    except Document.DoesNotExist:
        return
    build_or_update_fingerprint(doc)
    try:
        scan_near_duplicates_for_document(doc)
    except Exception:
        logger.exception("Near-duplicate scan failed for %s", document_id)
