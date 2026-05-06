"""Anchor revocation / dispute attestation service.

Auditors and admins can attach a structured revocation to a previously anchored
``BlockchainReceipt``. The original anchor is **never deleted** — the
revocation is an additive, non-repudiable counter-attestation. This is
critical for traceability: the audit trail must always show both sides.
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone

from apps.blockchain.gateway import get_blockchain_gateway
from apps.blockchain.models import AnchorRevocation, BlockchainReceipt
from apps.common.enums import BlockchainAnchorStatus

logger = logging.getLogger(__name__)


class RevocationError(Exception):
    pass


@dataclass
class RevocationOutcome:
    revocation: AnchorRevocation
    reason_hash: str


def _reason_hash(reason_code: str, reason_text: str, revoker_id) -> str:
    payload = {
        "schema": "smart-tobacco.anchor-revocation.v1",
        "reason_code": reason_code,
        "reason_text": reason_text,
        "revoker_id": str(revoker_id) if revoker_id else None,
        "issued_at": timezone.now().isoformat(),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def _original_anchor_id_hex(receipt: BlockchainReceipt) -> str:
    """Best-effort: derive a 32-byte 'anchor identifier' from the receipt.

    The smart contract's ``anchorEventHash`` returns its own ``bytes32``
    anchorId computed from data + timestamp + submitter. We don't always have
    that round-tripped here, so we use the receipt's ``data_hash`` as the
    revocation target — the tx_hash + reason_hash combination still uniquely
    identifies which anchor was disputed.
    """
    if receipt.data_hash and len(receipt.data_hash) == 64:
        return receipt.data_hash
    # Fallback: hash the tx_hash so we always have a 64-char hex.
    return hashlib.sha256((receipt.tx_hash or "").encode("utf-8")).hexdigest()


def revoke_anchor(
    *,
    target_receipt: BlockchainReceipt,
    revoker,
    reason_code: str,
    reason_text: str,
) -> RevocationOutcome:
    valid_codes = {c for c, _ in AnchorRevocation.REASON_CHOICES}
    if reason_code not in valid_codes:
        raise RevocationError(f"reason_code must be one of {sorted(valid_codes)}")
    if not reason_text or not reason_text.strip():
        raise RevocationError("reason_text is required")

    reason_hash = _reason_hash(reason_code, reason_text, getattr(revoker, "id", None))

    revocation = AnchorRevocation.objects.create(
        target_receipt=target_receipt,
        revoker=revoker,
        reason_code=reason_code,
        reason_text=reason_text,
        reason_hash=reason_hash,
        anchor_status=BlockchainAnchorStatus.PENDING,
    )

    gateway = get_blockchain_gateway()
    try:
        result = gateway.revoke_anchor(
            original_anchor_id_hex=_original_anchor_id_hex(target_receipt),
            reason_hash=reason_hash,
        )
    except Exception:
        logger.exception("Revocation %s anchor failed", revocation.id)
        revocation.anchor_status = BlockchainAnchorStatus.FAILED
        revocation.save(update_fields=["anchor_status", "updated_at"])
        raise

    with transaction.atomic():
        revocation.anchor_tx_hash = result.get("tx_hash") or ""
        revocation.anchor_status = (
            BlockchainAnchorStatus.CONFIRMED
            if result.get("status") == "CONFIRMED"
            else BlockchainAnchorStatus.SUBMITTED
        )
        revocation.save(update_fields=["anchor_tx_hash", "anchor_status", "updated_at"])
        BlockchainReceipt.objects.create(
            reference_type="anchor_revocation",
            reference_id=revocation.id,
            tx_hash=revocation.anchor_tx_hash or f"0x{revocation.id.hex}",
            block_number=result.get("block_number"),
            chain_id=result.get("chain_id", 1337),
            contract_address=result.get("contract_address", ""),
            method_name=result.get("method_name") or "revokeAnchor",
            data_hash=reason_hash,
            status=revocation.anchor_status,
            gas_used=result.get("gas_used"),
            raw_receipt=result,
        )

    return RevocationOutcome(revocation=revocation, reason_hash=reason_hash)


def list_revocations_for_receipt(receipt: BlockchainReceipt) -> list[AnchorRevocation]:
    return list(receipt.revocations.order_by("-created_at"))
