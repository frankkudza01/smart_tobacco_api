"""End-to-end tests for Tier 2/3 custody, inspection, and revocation flows.

All tests use the MockBlockchainGateway (BLOCKCHAIN_ENABLED=False, default in
config.settings.test). Real-chain behaviour is verified separately under
``tests/test_blockchain_hardhat.py`` (deployment-only).
"""
from __future__ import annotations

import pytest
from decimal import Decimal

from apps.blockchain.custody_service import (
    CustodyError,
    accept_custody_transfer,
    cancel_custody_transfer,
    decline_custody_transfer,
    initiate_custody_transfer,
    verify_stored_transfer,
)
from apps.blockchain.inspection_service import attest_inspection
from apps.blockchain.key_service import (
    get_address,
    get_or_create_signing_key,
    sign_message_for_user,
    verify_signature,
)
from apps.blockchain.models import (
    AnchorRevocation,
    BlockchainReceipt,
    CustodyStatus,
    CustodyTransfer,
    InspectionAttestation,
    UserSigningKey,
)
from apps.blockchain.passport_service import issue_passport, verify_passport_token
from apps.blockchain.reconciliation_service import reconcile_receipts, reconciliation_health
from apps.blockchain.revocation_service import revoke_anchor
from apps.common.enums import BlockchainAnchorStatus
from tests.factories import (
    AuditorFactory,
    BuyerFactory,
    FarmerFactory,
    LotFactory,
)


# ---------------------------------------------------------------------------
# Key service
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_signing_key_lazy_creation_and_idempotent(db):
    user = FarmerFactory()
    key1 = get_or_create_signing_key(user)
    key2 = get_or_create_signing_key(user)
    assert isinstance(key1, UserSigningKey)
    assert key1.id == key2.id
    assert key1.address == key2.address
    assert key1.address.startswith("0x") and len(key1.address) == 42


@pytest.mark.django_db
def test_sign_and_recover(db):
    user = FarmerFactory()
    address, sig = sign_message_for_user(user, "hello-world")
    assert verify_signature(message="hello-world", signature=sig, expected_address=address) is True
    assert verify_signature(message="forged", signature=sig, expected_address=address) is False


# ---------------------------------------------------------------------------
# Custody transfers
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_custody_initiate_creates_pending_with_from_signature(db, settings):
    settings.BLOCKCHAIN_ENABLED = False
    farmer = FarmerFactory()
    buyer = BuyerFactory()
    lot = LotFactory(farm__owner=farmer)

    out = initiate_custody_transfer(
        lot=lot, from_user=farmer, to_user=buyer, weight_kg=Decimal("123.456"),
    )
    t = out.transfer
    assert t.status == CustodyStatus.PENDING_ACCEPT
    assert t.from_signature.startswith("0x")
    assert t.to_signature == ""
    assert t.from_address == get_address(farmer)
    assert t.to_address == get_address(buyer)
    assert t.payload_hash == out.payload_hash


@pytest.mark.django_db
def test_custody_accept_anchors_and_collects_both_signatures(db, settings):
    settings.BLOCKCHAIN_ENABLED = False
    farmer = FarmerFactory()
    buyer = BuyerFactory()
    lot = LotFactory(farm__owner=farmer)

    out = initiate_custody_transfer(
        lot=lot, from_user=farmer, to_user=buyer, weight_kg=Decimal("100.0"),
    )
    accepted = accept_custody_transfer(transfer=out.transfer, accepting_user=buyer)
    t = accepted.transfer
    assert t.status == CustodyStatus.ANCHORED
    assert t.to_signature.startswith("0x")
    assert t.anchor_tx_hash.startswith("0x")
    assert t.anchor_status == BlockchainAnchorStatus.CONFIRMED
    assert t.anchored_at is not None
    receipt = BlockchainReceipt.objects.get(reference_id=t.id, reference_type="custody_transfer")
    assert receipt.tx_hash == t.anchor_tx_hash


@pytest.mark.django_db
def test_custody_verification_recovers_both_addresses(db, settings):
    settings.BLOCKCHAIN_ENABLED = False
    farmer, buyer = FarmerFactory(), BuyerFactory()
    lot = LotFactory(farm__owner=farmer)
    out = initiate_custody_transfer(lot=lot, from_user=farmer, to_user=buyer, weight_kg=1)
    accept_custody_transfer(transfer=out.transfer, accepting_user=buyer)
    out.transfer.refresh_from_db()

    report = verify_stored_transfer(out.transfer)
    assert report["from_signature_valid"] is True
    assert report["to_signature_valid"] is True
    assert report["payload_hash_matches"] is True
    assert report["anchored"] is True


@pytest.mark.django_db
def test_custody_decline_blocks_anchor(db, settings):
    settings.BLOCKCHAIN_ENABLED = False
    farmer, buyer = FarmerFactory(), BuyerFactory()
    lot = LotFactory(farm__owner=farmer)
    out = initiate_custody_transfer(lot=lot, from_user=farmer, to_user=buyer, weight_kg=1)
    decline_custody_transfer(transfer=out.transfer, declining_user=buyer)
    out.transfer.refresh_from_db()
    assert out.transfer.status == CustodyStatus.DECLINED
    with pytest.raises(CustodyError):
        accept_custody_transfer(transfer=out.transfer, accepting_user=buyer)


@pytest.mark.django_db
def test_custody_only_designated_recipient_can_accept(db, settings):
    settings.BLOCKCHAIN_ENABLED = False
    farmer, buyer, intruder = FarmerFactory(), BuyerFactory(), BuyerFactory()
    lot = LotFactory(farm__owner=farmer)
    out = initiate_custody_transfer(lot=lot, from_user=farmer, to_user=buyer, weight_kg=1)
    with pytest.raises(CustodyError, match="designated recipient"):
        accept_custody_transfer(transfer=out.transfer, accepting_user=intruder)


@pytest.mark.django_db
def test_custody_cancel_only_by_initiator(db, settings):
    settings.BLOCKCHAIN_ENABLED = False
    farmer, buyer = FarmerFactory(), BuyerFactory()
    lot = LotFactory(farm__owner=farmer)
    out = initiate_custody_transfer(lot=lot, from_user=farmer, to_user=buyer, weight_kg=1)
    with pytest.raises(CustodyError, match="initiator"):
        cancel_custody_transfer(transfer=out.transfer, cancelling_user=buyer)
    cancel_custody_transfer(transfer=out.transfer, cancelling_user=farmer)
    out.transfer.refresh_from_db()
    assert out.transfer.status == CustodyStatus.CANCELLED


# ---------------------------------------------------------------------------
# Inspection attestations
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_inspection_attest_creates_record_and_anchors(db, settings):
    settings.BLOCKCHAIN_ENABLED = False
    auditor = AuditorFactory()
    lot = LotFactory()
    out = attest_inspection(
        lot=lot, inspector=auditor, score=87,
        summary="Visual check passed", notes_uri="https://example.com/n.pdf",
    )
    a = out.attestation
    assert a.score == 87
    assert a.anchor_tx_hash.startswith("0x")
    assert a.anchor_status == BlockchainAnchorStatus.CONFIRMED
    assert BlockchainReceipt.objects.filter(
        reference_type="inspection_attestation", reference_id=a.id,
    ).exists()


@pytest.mark.django_db
def test_inspection_score_validation(db, settings):
    settings.BLOCKCHAIN_ENABLED = False
    auditor = AuditorFactory()
    lot = LotFactory()
    from apps.blockchain.inspection_service import InspectionError
    with pytest.raises(InspectionError):
        attest_inspection(lot=lot, inspector=auditor, score=150)


# ---------------------------------------------------------------------------
# Anchor revocation
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_revoke_anchor_creates_counter_attestation(db, settings):
    settings.BLOCKCHAIN_ENABLED = False
    auditor = AuditorFactory()
    farmer, buyer = FarmerFactory(), BuyerFactory()
    lot = LotFactory(farm__owner=farmer)
    # First create some anchored receipt to revoke (use a custody transfer).
    out = initiate_custody_transfer(lot=lot, from_user=farmer, to_user=buyer, weight_kg=1)
    accept_custody_transfer(transfer=out.transfer, accepting_user=buyer)
    receipt = BlockchainReceipt.objects.get(reference_id=out.transfer.id)

    rev_out = revoke_anchor(
        target_receipt=receipt,
        revoker=auditor,
        reason_code="DISPUTE",
        reason_text="Buyer claims wrong weight; investigating.",
    )
    rev = rev_out.revocation
    assert rev.reason_code == "DISPUTE"
    assert rev.anchor_tx_hash.startswith("0x")
    assert rev.anchor_status == BlockchainAnchorStatus.CONFIRMED
    # The original receipt is untouched (additive evidence).
    receipt.refresh_from_db()
    assert receipt.status == BlockchainAnchorStatus.CONFIRMED
    # And the revocation is queryable from the receipt side.
    assert receipt.revocations.count() == 1


# ---------------------------------------------------------------------------
# Reconciliation
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_reconciliation_marks_mock_chain_unverifiable(db, settings):
    settings.BLOCKCHAIN_ENABLED = False
    farmer, buyer = FarmerFactory(), BuyerFactory()
    lot = LotFactory(farm__owner=farmer)
    out = initiate_custody_transfer(lot=lot, from_user=farmer, to_user=buyer, weight_kg=1)
    accept_custody_transfer(transfer=out.transfer, accepting_user=buyer)
    outcome = reconcile_receipts()
    assert outcome.unverifiable >= 1
    assert outcome.drift == 0
    assert outcome.missing == 0
    health = reconciliation_health()
    assert health["blockchain_enabled"] is False
    assert "by_status" in health


# ---------------------------------------------------------------------------
# Passport (DB-backed: cross-checks the embedded anchor)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_passport_round_trip_with_no_anchor_yet(db, settings):
    """A lot with zero anchored events still issues a verifiable passport."""
    settings.BLOCKCHAIN_ENABLED = False
    settings.BLOCKCHAIN_PASSPORT_HMAC_SECRET = "passport-secret"
    lot = LotFactory()
    bundle = issue_passport(lot=lot, bale_index=1)
    assert bundle.token.count(".") == 1
    assert bundle.qr_text.startswith("smart-tobacco://passport?token=")
    report = verify_passport_token(bundle.token)
    assert report["ok"] is True
    assert report["signature_valid"] is True
    assert report["lot_id"] == str(lot.id)
    assert report["bale_index"] == 1


@pytest.mark.django_db
def test_passport_rejects_token_signed_with_other_secret(db, settings):
    settings.BLOCKCHAIN_ENABLED = False
    settings.BLOCKCHAIN_PASSPORT_HMAC_SECRET = "passport-secret"
    lot = LotFactory()
    bundle = issue_passport(lot=lot)
    settings.BLOCKCHAIN_PASSPORT_HMAC_SECRET = "rotated"
    report = verify_passport_token(bundle.token)
    assert report["ok"] is False
    assert report["error"] == "signature_invalid"
