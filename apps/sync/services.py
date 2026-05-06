import logging

from django.db import transaction

from apps.common.enums import SyncStatus
from apps.common.utils import compute_sha256_from_bytes
from apps.sync.models import SyncRecord

logger = logging.getLogger(__name__)

PAYLOAD_TYPE_HANDLERS = {}


def register_sync_handler(payload_type):
    def decorator(func):
        PAYLOAD_TYPE_HANDLERS[payload_type] = func
        return func
    return decorator


@register_sync_handler("farm")
def _handle_farm_sync(payload, actor):
    from apps.farms.models import Farm
    farm = Farm.objects.create(
        id=payload.get("id"),
        owner=actor,
        name=payload["name"],
        location_description=payload.get("location_description", ""),
        latitude=payload.get("latitude"),
        longitude=payload.get("longitude"),
        size_hectares=payload.get("size_hectares"),
        district=payload.get("district", ""),
        province=payload.get("province", ""),
    )
    return str(farm.id), "farm"


@register_sync_handler("season")
def _handle_season_sync(payload, actor):
    from apps.seasons.models import Season
    season = Season.objects.create(
        id=payload.get("id"),
        farm_id=payload["farm_id"],
        crop_year=payload["crop_year"],
        name=payload.get("name", ""),
        planting_date=payload.get("planting_date"),
        expected_harvest_date=payload.get("expected_harvest_date"),
    )
    return str(season.id), "season"


@register_sync_handler("lot")
def _handle_lot_sync(payload, actor):
    from apps.lots.models import Lot
    lot = Lot.objects.create(
        id=payload.get("id"),
        season_id=payload["season_id"],
        created_by=actor,
        lot_number=payload["lot_number"],
        description=payload.get("description", ""),
        weight_kg=payload.get("weight_kg"),
        bale_count=payload.get("bale_count", 1),
        tobacco_type=payload.get("tobacco_type", ""),
    )
    return str(lot.id), "lot"


@register_sync_handler("trace_event")
def _handle_trace_event_sync(payload, actor):
    from apps.traceability.services import create_trace_event
    from apps.lots.models import Lot
    lot = Lot.objects.get(id=payload["lot_id"])
    event = create_trace_event(
        lot=lot,
        actor=actor,
        event_type=payload["event_type"],
        timestamp=payload["timestamp"],
        location=payload.get("location", ""),
        latitude=payload.get("latitude"),
        longitude=payload.get("longitude"),
        payload=payload.get("payload", {}),
        notes=payload.get("notes", ""),
        prev_event_hash=payload.get("prev_event_hash"),
    )
    return str(event.id), "trace_event"


@register_sync_handler("document_meta")
def _handle_document_meta_sync(payload, actor):
    """
    Offline-first document metadata sync. Prefer `file_base64` for small files;
    otherwise creates a minimal placeholder file so the row can be anchored by hash later.
    """
    import base64

    from django.core.files.base import ContentFile

    from apps.common.access import can_view_lot
    from apps.documents.models import Document
    from apps.lots.models import Lot

    lot_id = payload.get("lot_id")
    if not lot_id:
        raise ValueError("lot_id is required for document_meta")
    lot = Lot.objects.select_related("season", "farm").filter(id=lot_id).first()
    if lot is None:
        raise ValueError("Lot not found")
    if not can_view_lot(actor, lot):
        raise ValueError("Not allowed to attach document to this lot")

    b64 = payload.get("file_base64")
    if b64:
        try:
            content = base64.b64decode(b64)
        except Exception as exc:
            raise ValueError(f"Invalid file_base64: {exc}") from exc
    else:
        content = b"[offline-sync-placeholder]\n"

    file_name = payload.get("file_name") or "synced-document.bin"
    doc = Document(
        id=payload.get("id"),
        lot=lot,
        uploaded_by=actor,
        document_type=payload["document_type"],
        title=payload.get("title") or "Synced document",
        description=payload.get("description", ""),
        file_name=file_name,
        mime_type=payload.get("mime_type", "application/octet-stream"),
        file_size=len(content),
        sha256_hash=payload.get("sha256_hash", ""),
    )
    doc.file.save(file_name, ContentFile(content), save=False)
    doc.save()
    return str(doc.id), "document"


@register_sync_handler("dispute")
def _handle_dispute_sync(payload, actor):
    from apps.disputes.models import Dispute
    dispute = Dispute.objects.create(
        id=payload.get("id"),
        lot_id=payload.get("lot_id"),
        sale_id=payload.get("sale_id"),
        raised_by=actor,
        title=payload["title"],
        description=payload["description"],
    )
    return str(dispute.id), "dispute"


def process_sync_record(record: SyncRecord):
    handler = PAYLOAD_TYPE_HANDLERS.get(record.payload_type)
    if not handler:
        record.status = SyncStatus.ERROR
        record.error_detail = f"Unknown payload_type: {record.payload_type}"
        record.save(update_fields=["status", "error_detail", "updated_at"])
        return

    try:
        with transaction.atomic():
            remote_id, remote_type = handler(record.payload, record.actor)
            record.remote_object_id = remote_id
            record.remote_object_type = remote_type
            record.status = SyncStatus.SYNCED
            record.save(update_fields=["remote_object_id", "remote_object_type", "status", "updated_at"])
    except Exception as exc:
        logger.exception("Sync processing failed for record %s", record.id)
        record.status = SyncStatus.ERROR
        record.error_detail = str(exc)[:2000]
        record.save(update_fields=["status", "error_detail", "updated_at"])


def process_batch_sync(records_data: list, actor) -> list:
    import json

    results = []
    for item in records_data:
        idempotency_key = item["idempotency_key"]

        existing = SyncRecord.objects.filter(idempotency_key=idempotency_key).first()
        if existing:
            results.append({
                "client_record_id": str(item["client_record_id"]),
                "idempotency_key": idempotency_key,
                "status": SyncStatus.DUPLICATE_IGNORED,
                "remote_object_id": str(existing.remote_object_id) if existing.remote_object_id else None,
            })
            continue

        payload_hash = compute_sha256_from_bytes(json.dumps(item["payload"], sort_keys=True).encode())

        record = SyncRecord.objects.create(
            actor=actor,
            client_record_id=item["client_record_id"],
            idempotency_key=idempotency_key,
            payload_type=item["payload_type"],
            payload_hash=payload_hash,
            payload=item["payload"],
        )

        process_sync_record(record)

        results.append({
            "client_record_id": str(record.client_record_id),
            "idempotency_key": record.idempotency_key,
            "status": record.status,
            "remote_object_id": str(record.remote_object_id) if record.remote_object_id else None,
            "error_detail": record.error_detail or None,
        })

    return results
