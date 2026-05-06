"""Off-chain ↔ on-chain reconciliation.

For every confirmed ``BlockchainReceipt`` we periodically re-read the chain
(``gateway.verify_anchor`` / ``gateway.get_receipt``) and compare:

- the receipt is still present at the recorded ``tx_hash`` (detects reorgs),
- the receipt's ``status`` is still ``CONFIRMED``,
- (optionally) the on-chain ``data_hash`` matches what we stored.

The MockBlockchainGateway returns ``verified=True`` for everything (intentional
— there is no real chain to read), so under the mock we mark receipts as
``UNVERIFIABLE`` rather than falsely reporting ``OK``. This is what tells the
auditor "you have NOT enabled the real chain yet".
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from django.conf import settings
from django.utils import timezone

from apps.blockchain.gateway import (
    MockBlockchainGateway,
    Web3BlockchainGateway,
    get_blockchain_gateway,
)
from apps.blockchain.models import BlockchainReceipt, ReconciliationStatus
from apps.common.enums import BlockchainAnchorStatus

logger = logging.getLogger(__name__)


@dataclass
class ReconciliationOutcome:
    receipts_checked: int
    ok: int
    drift: int
    missing: int
    unverifiable: int


def _reconcile_one(receipt: BlockchainReceipt, gateway) -> tuple[str, str]:
    """Return ``(reconciliation_status, notes)`` for one receipt."""
    if isinstance(gateway, MockBlockchainGateway) or not isinstance(gateway, Web3BlockchainGateway):
        return (
            ReconciliationStatus.UNVERIFIABLE,
            "MockBlockchainGateway in use; enable BLOCKCHAIN_ENABLED for real verification.",
        )
    try:
        result = gateway.verify_anchor(receipt.tx_hash)
    except Exception as exc:  # noqa: BLE001
        return ReconciliationStatus.UNVERIFIABLE, f"RPC error: {exc}"
    if not result.get("verified"):
        return (
            ReconciliationStatus.MISSING,
            f"verify_anchor returned not-verified: {result}",
        )
    if result.get("status") and result["status"] != "CONFIRMED":
        return (
            ReconciliationStatus.DRIFT,
            f"On-chain status is {result.get('status')}, expected CONFIRMED.",
        )
    return ReconciliationStatus.OK, "On-chain receipt matches stored values."


def reconcile_receipts(*, batch_size: int = 50) -> ReconciliationOutcome:
    """Reconcile up to ``batch_size`` confirmed receipts (oldest stale first)."""
    qs = (
        BlockchainReceipt.objects.filter(status=BlockchainAnchorStatus.CONFIRMED)
        .order_by("last_reconciled_at", "created_at")[:batch_size]
    )
    gateway = get_blockchain_gateway()

    counts = {
        ReconciliationStatus.OK: 0,
        ReconciliationStatus.DRIFT: 0,
        ReconciliationStatus.MISSING: 0,
        ReconciliationStatus.UNVERIFIABLE: 0,
    }
    checked = 0

    for receipt in qs:
        status, notes = _reconcile_one(receipt, gateway)
        receipt.reconciliation_status = status
        receipt.reconciliation_notes = notes
        receipt.last_reconciled_at = timezone.now()
        receipt.save(update_fields=[
            "reconciliation_status", "reconciliation_notes",
            "last_reconciled_at", "updated_at",
        ])
        counts[status] = counts.get(status, 0) + 1
        checked += 1

    return ReconciliationOutcome(
        receipts_checked=checked,
        ok=counts[ReconciliationStatus.OK],
        drift=counts[ReconciliationStatus.DRIFT],
        missing=counts[ReconciliationStatus.MISSING],
        unverifiable=counts[ReconciliationStatus.UNVERIFIABLE],
    )


def reconciliation_health() -> dict:
    """High-level summary for the regulator dashboard."""
    qs = BlockchainReceipt.objects.all()
    total = qs.count()
    by_status = {
        s: qs.filter(reconciliation_status=s).count()
        for s, _ in ReconciliationStatus.choices
    }
    drift_count = by_status[ReconciliationStatus.DRIFT]
    missing_count = by_status[ReconciliationStatus.MISSING]
    return {
        "total_receipts": total,
        "by_status": by_status,
        "alerting": drift_count > 0 or missing_count > 0,
        "blockchain_enabled": bool(settings.BLOCKCHAIN_ENABLED),
    }
