import logging

from apps.common.access import can_view_farm, can_view_lot
from apps.common.enums import SyncStatus
from apps.disputes.models import Dispute
from apps.documents.models import Document
from apps.documents.services import verify_document
from apps.farms.models import Farm
from apps.grading.models import GradeRecord
from apps.lots.models import Lot
from apps.provenance.models import ProvenanceQueryLog
from apps.sales.models import Sale
from apps.settlements.models import Settlement
from apps.sync.models import SyncRecord
from apps.sync.services import process_sync_record
from apps.traceability.models import TraceEvent

logger = logging.getLogger(__name__)


def get_lot_provenance(lot_id, queried_by=None):
    try:
        lot = Lot.objects.select_related("season", "farm", "farm__owner").get(id=lot_id)
    except Lot.DoesNotExist:
        return None

    events = TraceEvent.objects.filter(lot=lot).order_by("timestamp").values(
        "id", "event_type", "timestamp", "location", "actor__email",
        "prev_event_hash", "event_hash", "anchor_status", "anchor_tx_hash",
    )

    documents = Document.objects.filter(lot=lot).values(
        "id", "title", "document_type", "sha256_hash",
        "anchor_status", "created_at",
    )

    grades = GradeRecord.objects.filter(lot=lot).values(
        "id", "grade", "weight_kg", "graded_at", "graded_by__email",
    )

    sales = Sale.objects.filter(lot=lot).values(
        "id", "sale_type", "total_amount", "currency", "sale_date", "buyer__email",
    )

    settlements = Settlement.objects.filter(sale__lot=lot).values(
        "id", "amount_due", "amount_paid", "status", "payment_date",
    )

    disputes = Dispute.objects.filter(lot=lot).values(
        "id", "title", "status", "created_at",
    )

    provenance = {
        "lot": {
            "id": str(lot.id),
            "lot_number": lot.lot_number,
            "status": lot.status,
            "tobacco_type": lot.tobacco_type,
            "weight_kg": str(lot.weight_kg) if lot.weight_kg else None,
        },
        "farm": {
            "id": str(lot.farm.id),
            "name": lot.farm.name,
            "district": lot.farm.district,
            "province": lot.farm.province,
        },
        "farmer": {
            "name": lot.farm.owner.full_name,
        },
        "season": {
            "crop_year": lot.season.crop_year,
            "status": lot.season.status,
        },
        "timeline": list(events),
        "documents": list(documents),
        "grades": list(grades),
        "sales": list(sales),
        "settlements": list(settlements),
        "disputes": list(disputes),
    }

    if queried_by:
        ProvenanceQueryLog.objects.create(
            queried_by=queried_by,
            query_type="lot_provenance",
            reference_id=lot.id,
            reference_type="lot",
            result_summary={"lot_number": lot.lot_number, "event_count": len(provenance["timeline"])},
        )

    return provenance


def run_farm_provenance_checks(*, farm_id, queried_by):
    """
    Runs contractor-focused checks for one farm:
    - process pending sync records for this actor
    - recompute/verify document hashes
    - build provenance snapshots for accessible lots
    """
    try:
        farm = Farm.objects.get(id=farm_id)
    except Farm.DoesNotExist:
        return {"ok": False, "detail": "Farm not found."}

    if not can_view_farm(queried_by, farm):
        return {"ok": False, "detail": "Forbidden"}

    pending_sync_qs = SyncRecord.objects.filter(
        actor=queried_by,
        status=SyncStatus.PENDING_PROCESSING,
    ).order_by("created_at")[:50]

    sync_processed = 0
    sync_errors = 0
    for rec in pending_sync_qs:
        before = rec.status
        process_sync_record(rec)
        sync_processed += 1
        rec.refresh_from_db(fields=["status"])
        if rec.status == SyncStatus.ERROR and before != SyncStatus.ERROR:
            sync_errors += 1

    lots = Lot.objects.select_related("farm").filter(farm_id=farm.id).order_by("-created_at")
    accessible_lots = [lot for lot in lots if can_view_lot(queried_by, lot)]

    docs_verified = 0
    docs_failed = 0
    docs_blockchain_verified = 0
    for lot in accessible_lots:
        for doc in Document.objects.filter(lot=lot):
            result = verify_document(doc)
            if result.get("hash_match"):
                docs_verified += 1
            else:
                docs_failed += 1
            if result.get("blockchain_verified"):
                docs_blockchain_verified += 1

    provenance_checked = 0
    for lot in accessible_lots:
        out = get_lot_provenance(lot.id, queried_by=queried_by)
        if out is not None:
            provenance_checked += 1

    summary = {
        "ok": True,
        "farm_id": str(farm.id),
        "farm_name": farm.name,
        "lots_total": lots.count(),
        "lots_accessible": len(accessible_lots),
        "provenance_checked": provenance_checked,
        "documents_verified": docs_verified,
        "documents_failed": docs_failed,
        "documents_blockchain_verified": docs_blockchain_verified,
        "sync_processed": sync_processed,
        "sync_errors": sync_errors,
        "next_run_recommended_seconds": 60,
    }
    logger.info("Farm provenance checks completed: %s", summary)
    return summary
