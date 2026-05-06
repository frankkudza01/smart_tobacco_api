import logging

from celery import shared_task

from apps.common.enums import BlockchainAnchorStatus, DocumentVerificationState

logger = logging.getLogger(__name__)


def _is_valid_sha256_hex(value: str) -> bool:
    s = (value or "").strip()
    if len(s) == 66 and s.startswith("0x"):
        s = s[2:]
    if len(s) != 64:
        return False
    try:
        int(s, 16)
    except ValueError:
        return False
    return True


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def anchor_event_hash(self, trace_event_id: str):
    from apps.blockchain.gateway import get_blockchain_gateway
    from apps.blockchain.models import BlockchainReceipt
    from apps.traceability.models import TraceEvent

    try:
        event = TraceEvent.objects.get(id=trace_event_id)
    except TraceEvent.DoesNotExist:
        logger.error("TraceEvent %s not found", trace_event_id)
        return

    try:
        # Self-heal historical/invalid rows so anchoring can proceed safely.
        if not _is_valid_sha256_hex(event.event_hash):
            event.event_hash = event.compute_hash()
            event.save(update_fields=["event_hash", "updated_at"])

        gateway = get_blockchain_gateway()
        result = gateway.anchor_hash(
            data_hash=event.event_hash,
            reference_type="trace_event",
            reference_id=str(event.id),
        )

        BlockchainReceipt.objects.create(
            reference_type="trace_event",
            reference_id=event.id,
            tx_hash=result["tx_hash"],
            block_number=result.get("block_number"),
            chain_id=result.get("chain_id", 1337),
            contract_address=result.get("contract_address", ""),
            method_name="anchorEventHash",
            data_hash=event.event_hash,
            status=BlockchainAnchorStatus.CONFIRMED if result.get("status") == "CONFIRMED" else BlockchainAnchorStatus.SUBMITTED,
            gas_used=result.get("gas_used"),
            raw_receipt=result,
        )

        event.anchor_status = BlockchainAnchorStatus.CONFIRMED
        event.anchor_tx_hash = result["tx_hash"]
        event.save(update_fields=["anchor_status", "anchor_tx_hash", "updated_at"])

        logger.info("Anchored trace event %s: tx=%s", trace_event_id, result["tx_hash"])

    except ValueError:
        # Input validation errors (e.g. malformed hash) are not transient; don't retry.
        logger.exception("Blockchain anchoring validation failed for event %s", trace_event_id)
        event.anchor_status = BlockchainAnchorStatus.FAILED
        event.save(update_fields=["anchor_status", "updated_at"])
        return

    except Exception as exc:
        logger.exception("Blockchain anchoring failed for event %s", trace_event_id)
        event.anchor_status = BlockchainAnchorStatus.FAILED
        event.save(update_fields=["anchor_status", "updated_at"])
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def anchor_document_hash(self, document_id: str):
    from apps.blockchain.gateway import get_blockchain_gateway
    from apps.blockchain.models import BlockchainReceipt
    from apps.documents.models import Document

    try:
        doc = Document.objects.get(id=document_id)
    except Document.DoesNotExist:
        logger.error("Document %s not found", document_id)
        return

    gateway = get_blockchain_gateway()
    try:
        result = gateway.anchor_hash(
            data_hash=doc.sha256_hash,
            reference_type="document",
            reference_id=str(doc.id),
        )

        BlockchainReceipt.objects.create(
            reference_type="document",
            reference_id=doc.id,
            tx_hash=result["tx_hash"],
            block_number=result.get("block_number"),
            chain_id=result.get("chain_id", 1337),
            contract_address=result.get("contract_address", ""),
            method_name="anchorDocumentHash",
            data_hash=doc.sha256_hash,
            status=BlockchainAnchorStatus.CONFIRMED if result.get("status") == "CONFIRMED" else BlockchainAnchorStatus.SUBMITTED,
            gas_used=result.get("gas_used"),
            raw_receipt=result,
        )

        doc.anchor_status = BlockchainAnchorStatus.CONFIRMED
        doc.anchor_tx_hash = result["tx_hash"]
        doc.verification_state = DocumentVerificationState.ANCHORED
        doc.save(
            update_fields=["anchor_status", "anchor_tx_hash", "verification_state", "updated_at"]
        )

        logger.info("Anchored document %s: tx=%s", document_id, result["tx_hash"])

    except Exception as exc:
        logger.exception("Blockchain anchoring failed for document %s", document_id)
        doc.anchor_status = BlockchainAnchorStatus.FAILED
        doc.save(update_fields=["anchor_status", "updated_at"])
        raise self.retry(exc=exc)


@shared_task
def poll_pending_receipts():
    from apps.blockchain.gateway import get_blockchain_gateway
    from apps.blockchain.models import BlockchainReceipt

    pending = BlockchainReceipt.objects.filter(status=BlockchainAnchorStatus.SUBMITTED)
    gateway = get_blockchain_gateway()

    for receipt in pending[:50]:
        try:
            result = gateway.get_receipt(receipt.tx_hash)
            if result.get("status") == "CONFIRMED":
                receipt.status = BlockchainAnchorStatus.CONFIRMED
                receipt.block_number = result.get("block_number")
                receipt.gas_used = result.get("gas_used")
                receipt.save(update_fields=["status", "block_number", "gas_used", "updated_at"])
        except Exception:
            logger.warning("Failed to poll receipt %s", receipt.tx_hash)


@shared_task
def reconcile_anchored_receipts(batch_size: int = 50):
    """Periodic sweep: detect chain reorgs / drift between DB receipts and chain.

    Schedule via Celery beat (e.g. every 30 min). On the mock chain every
    receipt is marked UNVERIFIABLE — that's the signal for the operator that
    the real chain is not yet enabled.
    """
    from apps.blockchain.reconciliation_service import reconcile_receipts

    outcome = reconcile_receipts(batch_size=batch_size)
    logger.info(
        "Reconciliation sweep: checked=%d ok=%d drift=%d missing=%d unverifiable=%d",
        outcome.receipts_checked, outcome.ok, outcome.drift,
        outcome.missing, outcome.unverifiable,
    )
    return {
        "checked": outcome.receipts_checked,
        "ok": outcome.ok,
        "drift": outcome.drift,
        "missing": outcome.missing,
        "unverifiable": outcome.unverifiable,
    }


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def build_and_anchor_daily_event_batch(self, day_iso: str | None = None):
    """Build and anchor a Merkle batch for the given day (default: today, UTC).

    Designed to be scheduled once per day via Celery beat. Idempotent on
    ``batch_label`` so re-runs are safe. The empty-day case still anchors a
    GENESIS_EMPTY_ROOT attestation, which gives a continuous daily chain that
    auditors can sweep for missing days.
    """
    from datetime import datetime, timezone as dt_tz

    from apps.blockchain.merkle_service import build_and_anchor_event_batch

    day = None
    if day_iso:
        try:
            day = datetime.fromisoformat(day_iso)
            if day.tzinfo is None:
                day = day.replace(tzinfo=dt_tz.utc)
        except ValueError:
            logger.error("Invalid day_iso %s for build_and_anchor_daily_event_batch", day_iso)
            return

    try:
        result = build_and_anchor_event_batch(day=day)
        logger.info(
            "Daily Merkle batch %s: created=%s leaves=%d tx=%s",
            result.batch.batch_label, result.created, result.batch.leaf_count, result.batch.tx_hash,
        )
    except Exception as exc:
        logger.exception("build_and_anchor_daily_event_batch failed")
        raise self.retry(exc=exc)
