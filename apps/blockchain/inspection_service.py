"""TIMB / regulator inspection attestation service.

Anchors a structured inspection result on chain via ``attestInspection`` and
persists an off-chain ``InspectionAttestation`` row for fast querying. The
``data_hash`` covers the canonical inspection payload so the on-chain record
is tamper-evident even though the detailed text lives off-chain.
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.blockchain.gateway import get_blockchain_gateway
from apps.blockchain.key_service import get_or_create_signing_key
from apps.blockchain.models import BlockchainReceipt, InspectionAttestation
from apps.common.enums import BlockchainAnchorStatus

logger = logging.getLogger(__name__)


class InspectionError(Exception):
    pass


@dataclass
class InspectionOutcome:
    attestation: InspectionAttestation
    data_hash: str


def _canonical_inspection_payload(
    *,
    lot_id,
    inspector_address: str,
    score: int,
    summary: str,
    notes_uri: str,
    inspected_at: datetime,
    extra: dict[str, Any] | None = None,
) -> dict:
    return {
        "schema": "smart-tobacco.inspection.v1",
        "lot_id": str(lot_id),
        "inspector_address": inspector_address,
        "score": int(score),
        "summary": summary or "",
        "notes_uri": notes_uri or "",
        "inspected_at": inspected_at.isoformat(),
        "extra": extra or {},
    }


def _hash_payload(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def attest_inspection(
    *,
    lot,
    inspector,
    score: int,
    summary: str = "",
    notes_uri: str = "",
    inspected_at: datetime | None = None,
    extra: dict[str, Any] | None = None,
) -> InspectionOutcome:
    if not (0 <= int(score) <= 100):
        raise InspectionError("score must be between 0 and 100")

    inspected_at = inspected_at or timezone.now()
    inspector_key = get_or_create_signing_key(inspector)
    payload = _canonical_inspection_payload(
        lot_id=lot.id,
        inspector_address=inspector_key.address,
        score=score,
        summary=summary,
        notes_uri=notes_uri,
        inspected_at=inspected_at,
        extra=extra,
    )
    data_hash = _hash_payload(payload)

    attestation = InspectionAttestation.objects.create(
        lot=lot,
        inspector=inspector,
        inspector_address=inspector_key.address,
        score=int(score),
        summary=summary,
        notes_uri=notes_uri,
        data_hash=data_hash,
        inspected_at=inspected_at,
        anchor_status=BlockchainAnchorStatus.PENDING,
    )

    gateway = get_blockchain_gateway()
    try:
        result = gateway.attest_inspection(
            lot_id=str(lot.id),
            data_hash=data_hash,
            score=int(score),
            notes_uri=notes_uri,
        )
    except Exception:
        logger.exception("InspectionAttestation %s anchor failed", attestation.id)
        attestation.anchor_status = BlockchainAnchorStatus.FAILED
        attestation.save(update_fields=["anchor_status", "updated_at"])
        raise

    with transaction.atomic():
        attestation.anchor_tx_hash = result.get("tx_hash") or ""
        attestation.anchor_status = (
            BlockchainAnchorStatus.CONFIRMED
            if result.get("status") == "CONFIRMED"
            else BlockchainAnchorStatus.SUBMITTED
        )
        attestation.save(update_fields=["anchor_tx_hash", "anchor_status", "updated_at"])
        BlockchainReceipt.objects.create(
            reference_type="inspection_attestation",
            reference_id=attestation.id,
            tx_hash=attestation.anchor_tx_hash or f"0x{attestation.id.hex}",
            block_number=result.get("block_number"),
            chain_id=result.get("chain_id", 1337),
            contract_address=result.get("contract_address", ""),
            method_name=result.get("method_name") or "attestInspection",
            data_hash=data_hash,
            status=attestation.anchor_status,
            gas_used=result.get("gas_used"),
            raw_receipt=result,
        )

    return InspectionOutcome(attestation=attestation, data_hash=data_hash)


def list_inspections_for_lot(*, lot_id) -> list[InspectionAttestation]:
    return list(InspectionAttestation.objects.filter(lot_id=lot_id).order_by("-inspected_at"))
