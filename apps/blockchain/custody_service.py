"""
Co-signed custody-transfer service.

Two-step protocol so neither party can forge ownership unilaterally:

1. **Initiate** — the current holder (``from_user``) calls
   ``initiate_custody_transfer``. The server:
   - resolves both parties' signing addresses (lazily creating keypairs),
   - builds a canonical payload + payload hash,
   - asks the *from* user's keypair to ECDSA-sign the hash (EIP-191),
   - stores a ``CustodyTransfer`` row in ``PENDING_ACCEPT``.

2. **Accept** — the recipient (``to_user``) calls ``accept_custody_transfer``.
   The server:
   - re-derives the canonical payload + hash and checks they match what was
     stored (no tampering between steps),
   - re-verifies the *from* signature (still valid),
   - asks the *to* user's keypair to sign,
   - calls ``gateway.record_custody_transfer`` to emit ``CustodyTransferred``,
   - persists the on-chain receipt and the ``ANCHORED`` status.

Recipients can also ``decline`` instead of accepting. The original holder can
``cancel`` any ``PENDING_ACCEPT`` transfer they initiated.
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.blockchain.gateway import get_blockchain_gateway
from apps.blockchain.key_service import (
    get_or_create_signing_key,
    sign_message_for_user,
    verify_signature,
)
from apps.blockchain.models import (
    BlockchainReceipt,
    CustodyStatus,
    CustodyTransfer,
)
from apps.common.enums import BlockchainAnchorStatus

logger = logging.getLogger(__name__)


class CustodyError(Exception):
    """Raised by the service when the caller violates the protocol."""


@dataclass
class CustodyOutcome:
    transfer: CustodyTransfer
    payload_hash: str
    from_address: str
    to_address: str


def _canonical_payload(
    *,
    lot_id: str,
    from_address: str,
    to_address: str,
    weight_kg: Decimal,
    transfer_timestamp: datetime,
    notes: str,
) -> dict:
    return {
        "schema": "smart-tobacco.custody-transfer.v1",
        "lot_id": str(lot_id),
        "from_address": from_address,
        "to_address": to_address,
        "weight_kg": f"{Decimal(weight_kg):.3f}",
        "transfer_timestamp": transfer_timestamp.isoformat(),
        "notes": notes or "",
    }


def _payload_hash(payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _canonical_message(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True)


def initiate_custody_transfer(
    *,
    lot,
    from_user,
    to_user,
    weight_kg,
    transfer_timestamp: datetime | None = None,
    notes: str = "",
) -> CustodyOutcome:
    if from_user.id == to_user.id:
        raise CustodyError("from_user and to_user must differ")

    transfer_timestamp = transfer_timestamp or timezone.now()
    weight_kg = Decimal(str(weight_kg))
    if weight_kg <= 0:
        raise CustodyError("weight_kg must be > 0")

    from_key = get_or_create_signing_key(from_user)
    to_key = get_or_create_signing_key(to_user)

    payload = _canonical_payload(
        lot_id=lot.id,
        from_address=from_key.address,
        to_address=to_key.address,
        weight_kg=weight_kg,
        transfer_timestamp=transfer_timestamp,
        notes=notes,
    )
    payload_hash = _payload_hash(payload)
    message = _canonical_message(payload)
    from_signing_addr, from_sig = sign_message_for_user(from_user, message)
    assert from_signing_addr == from_key.address  # sanity

    with transaction.atomic():
        transfer = CustodyTransfer.objects.create(
            lot=lot,
            from_user=from_user,
            to_user=to_user,
            from_address=from_key.address,
            to_address=to_key.address,
            weight_kg=weight_kg,
            transfer_timestamp=transfer_timestamp,
            notes=notes,
            canonical_payload=payload,
            payload_hash=payload_hash,
            from_signature=from_sig,
            status=CustodyStatus.PENDING_ACCEPT,
        )
    logger.info("CustodyTransfer %s initiated by user %s", transfer.id, from_user.id)
    return CustodyOutcome(
        transfer=transfer,
        payload_hash=payload_hash,
        from_address=from_key.address,
        to_address=to_key.address,
    )


def _re_derive_and_check(transfer: CustodyTransfer) -> None:
    """Re-build canonical payload from stored fields, verify nothing drifted."""
    payload = _canonical_payload(
        lot_id=transfer.lot_id,
        from_address=transfer.from_address,
        to_address=transfer.to_address,
        weight_kg=transfer.weight_kg,
        transfer_timestamp=transfer.transfer_timestamp,
        notes=transfer.notes,
    )
    if _payload_hash(payload) != transfer.payload_hash:
        raise CustodyError("Stored payload hash does not match canonical re-derivation")
    if not verify_signature(
        message=_canonical_message(payload),
        signature=transfer.from_signature,
        expected_address=transfer.from_address,
    ):
        raise CustodyError("From-party signature is invalid")


def accept_custody_transfer(*, transfer: CustodyTransfer, accepting_user) -> CustodyOutcome:
    if transfer.status != CustodyStatus.PENDING_ACCEPT:
        raise CustodyError(f"Transfer is not pending acceptance (status={transfer.status})")
    if transfer.to_user_id and transfer.to_user_id != accepting_user.id:
        raise CustodyError("Only the designated recipient may accept this transfer")

    _re_derive_and_check(transfer)
    payload = transfer.canonical_payload
    message = _canonical_message(payload)
    to_addr, to_sig = sign_message_for_user(accepting_user, message)
    if to_addr.lower() != transfer.to_address.lower():
        raise CustodyError("Recipient signing address does not match the registered to_address")

    with transaction.atomic():
        transfer.to_signature = to_sig
        transfer.accepted_at = timezone.now()
        transfer.status = CustodyStatus.ACCEPTED_AWAITING_ANCHOR
        transfer.save(update_fields=["to_signature", "accepted_at", "status", "updated_at"])

    # Anchor on chain. We do NOT roll back the DB row if the anchor fails — the
    # off-chain co-signed proof is still valid evidence; the next reconciliation
    # sweep will retry.
    gateway = get_blockchain_gateway()
    try:
        result = gateway.record_custody_transfer(
            lot_id=str(transfer.lot_id),
            from_address=transfer.from_address,
            to_address=transfer.to_address,
            payload_hash=transfer.payload_hash,
            weight_grams=int(Decimal(transfer.weight_kg) * 1000),
            timestamp_unix=int(transfer.transfer_timestamp.timestamp()),
        )
    except Exception:
        logger.exception("CustodyTransfer %s anchor failed", transfer.id)
        transfer.anchor_status = BlockchainAnchorStatus.FAILED
        transfer.save(update_fields=["anchor_status", "updated_at"])
        raise

    with transaction.atomic():
        transfer.anchor_tx_hash = result.get("tx_hash") or ""
        transfer.anchor_status = (
            BlockchainAnchorStatus.CONFIRMED
            if result.get("status") == "CONFIRMED"
            else BlockchainAnchorStatus.SUBMITTED
        )
        transfer.anchored_at = timezone.now()
        transfer.status = CustodyStatus.ANCHORED
        transfer.save(
            update_fields=[
                "anchor_tx_hash", "anchor_status",
                "anchored_at", "status", "updated_at",
            ]
        )
        BlockchainReceipt.objects.create(
            reference_type="custody_transfer",
            reference_id=transfer.id,
            tx_hash=transfer.anchor_tx_hash or f"0x{transfer.id.hex}",
            block_number=result.get("block_number"),
            chain_id=result.get("chain_id", 1337),
            contract_address=result.get("contract_address", ""),
            method_name=result.get("method_name") or "recordCustodyTransfer",
            data_hash=transfer.payload_hash,
            status=transfer.anchor_status,
            gas_used=result.get("gas_used"),
            raw_receipt=result,
        )

    return CustodyOutcome(
        transfer=transfer,
        payload_hash=transfer.payload_hash,
        from_address=transfer.from_address,
        to_address=transfer.to_address,
    )


def decline_custody_transfer(*, transfer: CustodyTransfer, declining_user) -> CustodyTransfer:
    if transfer.status != CustodyStatus.PENDING_ACCEPT:
        raise CustodyError(f"Transfer is not pending (status={transfer.status})")
    if transfer.to_user_id and transfer.to_user_id != declining_user.id:
        raise CustodyError("Only the designated recipient may decline this transfer")
    transfer.status = CustodyStatus.DECLINED
    transfer.save(update_fields=["status", "updated_at"])
    return transfer


def cancel_custody_transfer(*, transfer: CustodyTransfer, cancelling_user) -> CustodyTransfer:
    if transfer.status != CustodyStatus.PENDING_ACCEPT:
        raise CustodyError(f"Transfer is not pending (status={transfer.status})")
    if transfer.from_user_id and transfer.from_user_id != cancelling_user.id:
        raise CustodyError("Only the initiator may cancel this transfer")
    transfer.status = CustodyStatus.CANCELLED
    transfer.save(update_fields=["status", "updated_at"])
    return transfer


def list_custody_for_lot(*, lot_id) -> list[CustodyTransfer]:
    return list(CustodyTransfer.objects.filter(lot_id=lot_id).order_by("-created_at"))


def verify_stored_transfer(transfer: CustodyTransfer) -> dict:
    """Public-style verification: anyone with the row can re-check both sigs."""
    payload = transfer.canonical_payload or {}
    message = _canonical_message(payload)
    payload_hash_matches = _payload_hash(payload) == transfer.payload_hash if payload else False
    from_ok = verify_signature(
        message=message,
        signature=transfer.from_signature,
        expected_address=transfer.from_address,
    ) if transfer.from_signature else False
    to_ok = verify_signature(
        message=message,
        signature=transfer.to_signature,
        expected_address=transfer.to_address,
    ) if transfer.to_signature else None  # None when not yet accepted
    return {
        "transfer_id": str(transfer.id),
        "payload_hash_matches": payload_hash_matches,
        "from_signature_valid": from_ok,
        "to_signature_valid": to_ok,
        "status": transfer.status,
        "anchored": transfer.status == CustodyStatus.ANCHORED,
        "anchor_tx_hash": transfer.anchor_tx_hash,
    }
