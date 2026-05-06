"""Integration tests for Merkle batch building, audit, and proof bundle round-trip."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from django.utils import timezone as django_tz

from apps.blockchain.merkle import compute_merkle_root, verify_inclusion_proof
from apps.blockchain.merkle_service import (
    audit_lot_chain,
    build_and_anchor_event_batch,
    build_inclusion_proof,
    build_proof_bundle,
    find_batch_for_event,
)
from apps.blockchain.models import BlockchainReceipt, MerkleAnchorBatch
from apps.blockchain.verifier import verify_proof_bundle
from apps.common.enums import BlockchainAnchorStatus, TraceEventType
from apps.traceability.models import TraceEvent
from tests.factories import LotFactory


def _make_event(lot, *, idx: int) -> TraceEvent:
    """Bypass the celery enqueue path and create an event with chained hashes."""
    event = TraceEvent(
        lot=lot,
        actor=lot.farm.owner,
        event_type=TraceEventType.PLANTING if idx == 0 else TraceEventType.HARVESTING,
        timestamp=django_tz.now(),
        location=f"Field {idx}",
        payload={"step": idx},
    )
    event.save()
    return event


@pytest.mark.django_db
def test_build_and_anchor_today_creates_batch_with_correct_root(db, settings):
    """End-to-end: 3 events on a lot today → batch is built, anchored, and root matches."""
    settings.BLOCKCHAIN_ENABLED = False  # use MockBlockchainGateway
    lot = LotFactory()
    events = [_make_event(lot, idx=i) for i in range(3)]
    expected_root = compute_merkle_root([e.event_hash for e in events])

    result = build_and_anchor_event_batch()

    assert result.created is True
    batch = result.batch
    assert batch.leaf_count == 3
    assert batch.merkle_root == expected_root
    assert batch.anchor_status == BlockchainAnchorStatus.CONFIRMED
    assert batch.tx_hash.startswith("0x")
    assert BlockchainReceipt.objects.filter(reference_id=batch.id).count() == 1


@pytest.mark.django_db
def test_build_and_anchor_today_is_idempotent(db, settings):
    settings.BLOCKCHAIN_ENABLED = False
    lot = LotFactory()
    _make_event(lot, idx=0)

    first = build_and_anchor_event_batch()
    second = build_and_anchor_event_batch()

    assert first.created is True
    assert second.created is False
    assert second.skipped_reason == "already_exists"
    assert MerkleAnchorBatch.objects.count() == 1


@pytest.mark.django_db
def test_inclusion_proof_round_trips_for_each_event(db, settings):
    settings.BLOCKCHAIN_ENABLED = False
    lot = LotFactory()
    events = [_make_event(lot, idx=i) for i in range(5)]
    build_and_anchor_event_batch()

    for ev in events:
        batch, idx = find_batch_for_event(trace_event_id=ev.id)
        assert batch is not None
        assert idx is not None
        proof = build_inclusion_proof(batch=batch, leaf_index=idx)
        assert verify_inclusion_proof(ev.event_hash, proof, batch.merkle_root) is True


@pytest.mark.django_db
def test_audit_detects_event_hash_tampering(db, settings):
    settings.BLOCKCHAIN_ENABLED = False
    lot = LotFactory()
    [_make_event(lot, idx=i) for i in range(3)]
    build_and_anchor_event_batch()

    # Mutate the second event's stored hash without recomputing.
    second = TraceEvent.objects.filter(lot=lot).order_by("created_at", "id")[1]
    second.event_hash = "f" * 64
    super(TraceEvent, second).save(update_fields=["event_hash"])  # bypass chain validation

    report = audit_lot_chain(lot_id=lot.id)
    assert report["events_tampered"] >= 1
    assert report["merkle_intact"] is False
    tampered_row = next(r for r in report["events"] if r["event_id"] == str(second.id))
    assert tampered_row["hash_match"] is False
    assert tampered_row["inclusion_verified"] is False


@pytest.mark.django_db
def test_audit_passes_when_chain_is_clean(db, settings):
    settings.BLOCKCHAIN_ENABLED = False
    lot = LotFactory()
    [_make_event(lot, idx=i) for i in range(4)]
    build_and_anchor_event_batch()

    report = audit_lot_chain(lot_id=lot.id)
    assert report["events_tampered"] == 0
    assert report["chain_intact"] is True
    assert report["merkle_intact"] is True


@pytest.mark.django_db
def test_proof_bundle_is_independently_verifiable(db, settings):
    """The standalone verifier must accept the bundle produced by the service."""
    settings.BLOCKCHAIN_ENABLED = False
    lot = LotFactory()
    [_make_event(lot, idx=i) for i in range(4)]
    build_and_anchor_event_batch()

    bundle = build_proof_bundle(lot_id=lot.id)
    assert bundle["ok"] is True
    assert bundle["schema"] == "smart-tobacco.proof-bundle.v1"
    assert len(bundle["events"]) == 4
    for ev in bundle["events"]:
        assert ev["anchor"] is not None
        assert ev["merkle_proof"] is not None

    report = verify_proof_bundle(bundle)
    assert report["ok"] is True
    assert report["all_event_hashes_match"] is True
    assert report["chain_intact"] is True
    assert report["merkle_intact"] is True


@pytest.mark.django_db
def test_proof_bundle_verifier_detects_tampered_payload(db, settings):
    """Mutating the canonical payload after export must break verification."""
    settings.BLOCKCHAIN_ENABLED = False
    lot = LotFactory()
    [_make_event(lot, idx=i) for i in range(2)]
    build_and_anchor_event_batch()

    bundle = build_proof_bundle(lot_id=lot.id)
    bundle["events"][0]["canonical_payload"]["payload"] = {"step": 999}  # forge

    report = verify_proof_bundle(bundle)
    assert report["ok"] is False
    assert report["all_event_hashes_match"] is False
    assert report["events"][0]["hash_match"] is False


@pytest.mark.django_db
def test_empty_day_still_anchors_genesis_root(db, settings):
    """A day with zero qualifying events still produces a verifiable attestation."""
    from apps.blockchain.merkle import GENESIS_EMPTY_ROOT

    settings.BLOCKCHAIN_ENABLED = False
    # Build a window pointed at a day far in the past with zero events.
    past_day = datetime(2020, 1, 1, tzinfo=timezone.utc)
    result = build_and_anchor_event_batch(day=past_day)
    assert result.created is True
    assert result.batch.leaf_count == 0
    assert result.batch.merkle_root == GENESIS_EMPTY_ROOT
    assert result.batch.anchor_status == BlockchainAnchorStatus.CONFIRMED
