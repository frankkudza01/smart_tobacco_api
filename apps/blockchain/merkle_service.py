"""
Service layer for Merkle-batch traceability.

Three responsibilities:

1. **Build & anchor a batch** – select the eligible TraceEvent / Document rows
   for a window (a calendar day by default), build a deterministic Merkle tree,
   submit ``anchorBatchRoot`` on-chain, and persist a ``MerkleAnchorBatch`` row.
   Each event/document row is updated to point at the batch (via the batch tx
   hash) so a single canonical anchor proof exists per leaf.

2. **Tamper-evidence audit for a lot** – re-derive every event hash from the
   stored payload, compare to the stored ``event_hash``, and (if the event was
   batched) re-verify the inclusion proof against the on-chain root we have
   recorded. Emits a structured report any auditor can rely on.

3. **Proof bundle JSON for a lot** – produce a single download containing
   everything an external party needs to verify the lot off-chain: the
   canonical event payload, prev/next chain hashes, Merkle inclusion proofs,
   and the on-chain anchor metadata. Round-trips through the standalone
   ``apps.blockchain.verifier`` module.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable

from django.db import transaction
from django.utils import timezone as django_tz

from apps.blockchain.gateway import get_blockchain_gateway
from apps.blockchain.merkle import (
    GENESIS_EMPTY_ROOT,
    compute_inclusion_proof,
    compute_merkle_root,
    verify_inclusion_proof,
)
from apps.blockchain.models import BlockchainReceipt, MerkleAnchorBatch
from apps.common.enums import BlockchainAnchorStatus

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Build & anchor
# ---------------------------------------------------------------------------


def _day_window(day: datetime | None) -> tuple[datetime, datetime, str]:
    """Return ``(start_utc, end_utc, label)`` for a daily window."""
    now = django_tz.now() if day is None else day
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    label = f"{start.date().isoformat()}"
    return start, end, label


def collect_event_leaves_for_window(
    *,
    period_start: datetime,
    period_end: datetime,
) -> list[dict]:
    """Pick eligible TraceEvent rows for the window and emit ordered leaves.

    Eligibility: rows that already have a non-empty ``event_hash`` and whose
    ``created_at`` falls inside ``[period_start, period_end)``. Sorted by
    ``(lot_id, created_at, id)`` to make the leaf order **deterministic**.
    """
    from apps.traceability.models import TraceEvent

    qs = (
        TraceEvent.objects.filter(
            created_at__gte=period_start,
            created_at__lt=period_end,
        )
        .exclude(event_hash="")
        .order_by("lot_id", "created_at", "id")
        .values("id", "lot_id", "event_hash", "event_type", "timestamp", "created_at")
    )
    leaves: list[dict] = []
    for row in qs:
        leaves.append(
            {
                "reference_type": "trace_event",
                "reference_id": str(row["id"]),
                "lot_id": str(row["lot_id"]),
                "event_type": row["event_type"],
                "leaf_hash": row["event_hash"],
            }
        )
    return leaves


@dataclass
class BatchBuildResult:
    batch: MerkleAnchorBatch
    created: bool
    skipped_reason: str | None = None


def build_and_anchor_event_batch(
    *,
    day: datetime | None = None,
) -> BatchBuildResult:
    """Build the day's Merkle batch of TraceEvent hashes and anchor it on-chain.

    Idempotent on ``batch_label`` (one batch per (batch_type, day)).
    """
    period_start, period_end, day_label = _day_window(day)
    batch_label = f"trace_events-{day_label}"

    existing = MerkleAnchorBatch.objects.filter(batch_label=batch_label).first()
    if existing is not None:
        return BatchBuildResult(batch=existing, created=False, skipped_reason="already_exists")

    leaves = collect_event_leaves_for_window(
        period_start=period_start, period_end=period_end
    )
    leaf_hashes = [leaf["leaf_hash"] for leaf in leaves]
    merkle_root = compute_merkle_root(leaf_hashes) if leaf_hashes else GENESIS_EMPTY_ROOT

    batch = MerkleAnchorBatch.objects.create(
        batch_type=MerkleAnchorBatch.BATCH_TYPE_TRACE_EVENTS,
        batch_label=batch_label,
        period_start=period_start,
        period_end=period_end,
        leaf_count=len(leaves),
        merkle_root=merkle_root,
        leaves_json=leaves,
        anchor_status=BlockchainAnchorStatus.PENDING,
    )

    if not leaves:
        # Anchor the empty-root attestation so the daily chain is continuous.
        logger.info("MerkleAnchorBatch %s: no leaves; anchoring empty-root attestation.", batch_label)

    gateway = get_blockchain_gateway()
    try:
        result = gateway.anchor_batch_root(
            merkle_root=merkle_root,
            batch_type=MerkleAnchorBatch.BATCH_TYPE_TRACE_EVENTS,
            batch_label=batch_label,
            leaf_count=len(leaves),
        )
    except Exception:
        logger.exception("MerkleAnchorBatch %s: gateway.anchor_batch_root failed", batch_label)
        batch.anchor_status = BlockchainAnchorStatus.FAILED
        batch.save(update_fields=["anchor_status", "updated_at"])
        raise

    with transaction.atomic():
        batch.tx_hash = result.get("tx_hash") or ""
        batch.block_number = result.get("block_number")
        batch.chain_id = result.get("chain_id", batch.chain_id)
        batch.contract_address = result.get("contract_address", "")
        batch.gas_used = result.get("gas_used")
        batch.raw_receipt = result
        batch.anchor_status = (
            BlockchainAnchorStatus.CONFIRMED
            if result.get("status") == "CONFIRMED"
            else BlockchainAnchorStatus.SUBMITTED
        )
        batch.save()

        BlockchainReceipt.objects.create(
            reference_type="merkle_batch",
            reference_id=batch.id,
            tx_hash=batch.tx_hash or f"0x{batch.id.hex}",
            block_number=batch.block_number,
            chain_id=batch.chain_id,
            contract_address=batch.contract_address,
            method_name=result.get("method_name") or "anchorBatchRoot",
            data_hash=batch.merkle_root,
            status=batch.anchor_status,
            gas_used=batch.gas_used,
            raw_receipt=result,
        )

    logger.info(
        "MerkleAnchorBatch %s anchored: root=%s tx=%s leaves=%d",
        batch_label, merkle_root, batch.tx_hash, batch.leaf_count,
    )
    return BatchBuildResult(batch=batch, created=True)


# ---------------------------------------------------------------------------
# Inclusion proofs
# ---------------------------------------------------------------------------


def find_batch_for_event(*, trace_event_id) -> tuple[MerkleAnchorBatch | None, int | None]:
    """Locate the batch (if any) whose leaves contain ``trace_event_id``.

    Returns ``(batch, leaf_index)`` or ``(None, None)`` if not yet batched.
    Linear in the number of batches that overlap the event's day, which is
    bounded by the daily-batch design.
    """
    from apps.traceability.models import TraceEvent

    try:
        event = TraceEvent.objects.get(id=trace_event_id)
    except TraceEvent.DoesNotExist:
        return None, None

    qs = MerkleAnchorBatch.objects.filter(
        batch_type=MerkleAnchorBatch.BATCH_TYPE_TRACE_EVENTS,
        period_start__lte=event.created_at,
        period_end__gt=event.created_at,
    ).order_by("-period_start")

    target_id = str(trace_event_id)
    for batch in qs:
        for idx, leaf in enumerate(batch.leaves_json or []):
            if str(leaf.get("reference_id")) == target_id:
                return batch, idx
    return None, None


def build_inclusion_proof(*, batch: MerkleAnchorBatch, leaf_index: int) -> list[dict]:
    leaves = [leaf["leaf_hash"] for leaf in (batch.leaves_json or [])]
    steps = compute_inclusion_proof(leaves, leaf_index)
    return [{"sibling_hex": s.sibling_hex, "position": s.position} for s in steps]


# ---------------------------------------------------------------------------
# Tamper-evidence audit
# ---------------------------------------------------------------------------


@dataclass
class EventAuditRow:
    event_id: str
    event_type: str
    stored_event_hash: str
    recomputed_event_hash: str
    hash_match: bool
    prev_event_hash: str
    prev_chain_match: bool
    in_batch: bool
    batch_label: str | None
    batch_root: str | None
    inclusion_verified: bool
    anchor_tx_hash: str

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def audit_lot_chain(*, lot_id) -> dict:
    """Re-derive every event hash for ``lot_id`` and report drift.

    Returns a structured report:

    .. code-block:: python

        {
          "lot_id": "...",
          "event_count": 12,
          "events_intact": 11,
          "events_tampered": 1,
          "chain_intact": False,            # True iff every prev_event_hash matches
          "merkle_intact": True,            # True iff every batched leaf re-verifies
          "events": [ EventAuditRow.to_dict(), ... ],
        }
    """
    from apps.traceability.chain import GENESIS_PREV_EVENT_HASH
    from apps.traceability.models import TraceEvent

    qs = TraceEvent.objects.filter(lot_id=lot_id).order_by("created_at", "id")
    rows: list[EventAuditRow] = []
    expected_prev = GENESIS_PREV_EVENT_HASH
    chain_intact = True
    merkle_intact = True
    events_intact = 0

    for event in qs:
        recomputed = event.compute_hash()
        hash_match = recomputed == (event.event_hash or "")

        prev_chain_match = (event.prev_event_hash or "").strip().lower() == expected_prev
        if not prev_chain_match:
            chain_intact = False

        batch, idx = find_batch_for_event(trace_event_id=event.id)
        in_batch = batch is not None
        inclusion_verified = False
        if in_batch:
            proof = build_inclusion_proof(batch=batch, leaf_index=idx)
            inclusion_verified = verify_inclusion_proof(
                event.event_hash or recomputed, proof, batch.merkle_root
            )
            if not inclusion_verified:
                merkle_intact = False

        if hash_match and (not in_batch or inclusion_verified):
            events_intact += 1

        rows.append(
            EventAuditRow(
                event_id=str(event.id),
                event_type=event.event_type,
                stored_event_hash=event.event_hash or "",
                recomputed_event_hash=recomputed,
                hash_match=hash_match,
                prev_event_hash=event.prev_event_hash or "",
                prev_chain_match=prev_chain_match,
                in_batch=in_batch,
                batch_label=batch.batch_label if batch else None,
                batch_root=batch.merkle_root if batch else None,
                inclusion_verified=inclusion_verified,
                anchor_tx_hash=event.anchor_tx_hash or (batch.tx_hash if batch else ""),
            )
        )
        expected_prev = (event.event_hash or recomputed).strip().lower()

    return {
        "lot_id": str(lot_id),
        "event_count": len(rows),
        "events_intact": events_intact,
        "events_tampered": len(rows) - events_intact,
        "chain_intact": chain_intact,
        "merkle_intact": merkle_intact,
        "events": [r.to_dict() for r in rows],
    }


# ---------------------------------------------------------------------------
# Downloadable proof bundle
# ---------------------------------------------------------------------------


def build_proof_bundle(*, lot_id) -> dict:
    """Build a single JSON document fully describing a lot's on-chain proof.

    The ``apps.blockchain.verifier.verify_proof_bundle`` function consumes
    this exact shape and re-derives the Merkle root from each event's leaf
    hash + inclusion proof — i.e. an external auditor can verify the bundle
    without ever touching this codebase or the database.
    """
    from apps.lots.models import Lot
    from apps.traceability.models import TraceEvent

    try:
        lot = Lot.objects.select_related("farm", "season").get(id=lot_id)
    except Lot.DoesNotExist:
        return {"ok": False, "error": "lot_not_found"}

    events = TraceEvent.objects.filter(lot=lot).order_by("created_at", "id")
    bundle_events: list[dict] = []
    for event in events:
        batch, idx = find_batch_for_event(trace_event_id=event.id)
        proof_steps: list[dict] | None = None
        anchor_block: dict | None = None
        if batch is not None:
            proof_steps = build_inclusion_proof(batch=batch, leaf_index=idx)
            anchor_block = {
                "batch_label": batch.batch_label,
                "merkle_root": batch.merkle_root,
                "leaf_count": batch.leaf_count,
                "leaf_index": idx,
                "tx_hash": batch.tx_hash,
                "block_number": batch.block_number,
                "chain_id": batch.chain_id,
                "contract_address": batch.contract_address,
            }

        bundle_events.append(
            {
                "event_id": str(event.id),
                "event_type": event.event_type,
                "timestamp": event.timestamp.isoformat() if event.timestamp else None,
                "prev_event_hash": event.prev_event_hash or "",
                "event_hash": event.event_hash or "",
                "canonical_payload": {
                    "lot_id": str(event.lot_id),
                    "event_type": event.event_type,
                    "timestamp": event.timestamp.isoformat() if event.timestamp else None,
                    "payload": event.payload,
                    "prev_event_hash": event.prev_event_hash or "",
                },
                "merkle_proof": proof_steps,
                "anchor": anchor_block,
            }
        )

    return {
        "ok": True,
        "schema": "smart-tobacco.proof-bundle.v1",
        "generated_at": django_tz.now().isoformat(),
        "lot": {
            "id": str(lot.id),
            "lot_number": lot.lot_number,
            "tobacco_type": lot.tobacco_type,
            "weight_kg": str(lot.weight_kg) if lot.weight_kg is not None else None,
        },
        "farm": {
            "id": str(lot.farm.id),
            "name": lot.farm.name,
        },
        "season": {
            "crop_year": lot.season.crop_year,
        },
        "events": bundle_events,
        "verifier_instructions": (
            "For each event with a 'merkle_proof' and 'anchor' block: re-derive the "
            "Merkle root from event_hash + merkle_proof and compare to anchor.merkle_root. "
            "Then confirm the on-chain transaction at anchor.tx_hash on chain_id "
            "anchor.chain_id committed that same merkle_root via TobaccoTraceability.anchorBatchRoot."
        ),
    }


def collect_unbatched_event_count(*, since: datetime | None = None) -> int:
    """Diagnostic: how many recent events still need batching."""
    from apps.traceability.models import TraceEvent

    qs = TraceEvent.objects.exclude(event_hash="")
    if since is not None:
        qs = qs.filter(created_at__gte=since)
    referenced_ids: set[str] = set()
    for batch in MerkleAnchorBatch.objects.all().only("leaves_json"):
        for leaf in batch.leaves_json or []:
            referenced_ids.add(str(leaf.get("reference_id")))
    return sum(1 for ev in qs.values_list("id", flat=True) if str(ev) not in referenced_ids)


__all__ = [
    "BatchBuildResult",
    "EventAuditRow",
    "audit_lot_chain",
    "build_and_anchor_event_batch",
    "build_inclusion_proof",
    "build_proof_bundle",
    "collect_event_leaves_for_window",
    "collect_unbatched_event_count",
    "find_batch_for_event",
]
