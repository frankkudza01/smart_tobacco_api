"""
Bale-level "lot passport" — an HMAC-signed, QR-friendly token.

A passport token is a single short string a buyer / consumer can scan from a
printed bale label. It encodes:

* the lot id,
* the most recent on-chain anchor for that lot (Merkle batch tx, root),
* a generation timestamp,
* an **HMAC-SHA256 signature** computed with a server-side secret (settings
  ``BLOCKCHAIN_PASSPORT_HMAC_SECRET``, falling back to ``SECRET_KEY``).

Anyone can verify the token *offline* w.r.t. the HMAC (proving the platform
authored it) and *online* by hitting ``/api/v1/blockchain/public/passport/verify/?token=…``,
which also checks the embedded anchor against the live database.

Why HMAC and not ECDSA here?
----------------------------
- The QR must be **short** so it survives bale-printer resolution.
- We do not need third-party-recoverable signatures (the smart contract is the
  source of trust). HMAC + a public verify endpoint is the right trade-off:
  cheap to generate, cheap to verify, length-friendly.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import datetime, timezone

from django.conf import settings

from apps.blockchain.models import BlockchainReceipt, MerkleAnchorBatch
from apps.blockchain.merkle_service import find_batch_for_event


_PASSPORT_SCHEMA = "smart-tobacco.passport.v1"


def _hmac_secret() -> bytes:
    raw = getattr(settings, "BLOCKCHAIN_PASSPORT_HMAC_SECRET", None)
    if not raw:
        raw = settings.SECRET_KEY
    return raw.encode("utf-8") if isinstance(raw, str) else raw


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    padding = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode((s + padding).encode("ascii"))


def _sign_payload(payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    sig = hmac.new(_hmac_secret(), canonical, hashlib.sha256).digest()
    return _b64url(canonical) + "." + _b64url(sig)


def _verify_signature(token: str) -> tuple[dict, bool]:
    try:
        body_b64, sig_b64 = token.split(".", 1)
        body = _b64url_decode(body_b64)
        sig = _b64url_decode(sig_b64)
    except Exception:
        return {}, False
    expected = hmac.new(_hmac_secret(), body, hashlib.sha256).digest()
    if not hmac.compare_digest(expected, sig):
        return {}, False
    try:
        payload = json.loads(body.decode("utf-8"))
    except Exception:
        return {}, False
    return payload, True


@dataclass
class PassportBundle:
    token: str
    payload: dict
    qr_text: str  # exactly what should be encoded into the QR


def _latest_anchor_for_lot(lot_id) -> dict:
    """Best-effort: locate the most recent on-chain anchor for any of this lot's events."""
    from apps.traceability.models import TraceEvent

    latest_event = (
        TraceEvent.objects.filter(lot_id=lot_id)
        .exclude(event_hash="")
        .order_by("-created_at", "-id")
        .first()
    )
    if latest_event is None:
        return {}

    batch, idx = find_batch_for_event(trace_event_id=latest_event.id)
    if batch is not None:
        return {
            "kind": "merkle_batch",
            "batch_label": batch.batch_label,
            "merkle_root": batch.merkle_root,
            "leaf_index": idx,
            "tx_hash": batch.tx_hash,
            "block_number": batch.block_number,
            "chain_id": batch.chain_id,
            "contract_address": batch.contract_address,
        }
    # Fall back to the per-event receipt.
    receipt = (
        BlockchainReceipt.objects.filter(reference_type="trace_event", reference_id=latest_event.id)
        .order_by("-created_at")
        .first()
    )
    if receipt is None:
        return {}
    return {
        "kind": "trace_event",
        "tx_hash": receipt.tx_hash,
        "data_hash": receipt.data_hash,
        "block_number": receipt.block_number,
        "chain_id": receipt.chain_id,
        "contract_address": receipt.contract_address,
    }


def issue_passport(*, lot, bale_index: int | None = None) -> PassportBundle:
    """Build, sign, and return the lot passport token for a single bale.

    ``bale_index`` is optional — if provided, it is included in the payload so
    each printed bale carries its own unique token but they all share the same
    underlying anchor.
    """
    payload = {
        "schema": _PASSPORT_SCHEMA,
        "lot_id": str(lot.id),
        "lot_number": lot.lot_number,
        "tobacco_type": lot.tobacco_type,
        "bale_index": int(bale_index) if bale_index is not None else None,
        "issued_at": datetime.now(tz=timezone.utc).isoformat(),
        "anchor": _latest_anchor_for_lot(lot.id),
    }
    token = _sign_payload(payload)
    qr_text = f"smart-tobacco://passport?token={token}"
    return PassportBundle(token=token, payload=payload, qr_text=qr_text)


def verify_passport_token(token: str, *, allow_unanchored: bool = True) -> dict:
    """Verify HMAC + cross-check the embedded anchor against the live DB."""
    payload, ok = _verify_signature(token)
    if not ok:
        return {"ok": False, "error": "signature_invalid"}
    if payload.get("schema") != _PASSPORT_SCHEMA:
        return {"ok": False, "error": "unknown_schema", "schema": payload.get("schema")}

    anchor = payload.get("anchor") or {}
    lot_id = payload.get("lot_id")
    on_chain_match = None

    if anchor.get("kind") == "merkle_batch":
        batch = MerkleAnchorBatch.objects.filter(
            batch_label=anchor.get("batch_label")
        ).first()
        on_chain_match = (
            batch is not None
            and batch.merkle_root == anchor.get("merkle_root")
            and batch.tx_hash == anchor.get("tx_hash")
        )
    elif anchor.get("kind") == "trace_event":
        receipt = BlockchainReceipt.objects.filter(tx_hash=anchor.get("tx_hash")).first()
        on_chain_match = (
            receipt is not None
            and receipt.data_hash == anchor.get("data_hash")
        )
    elif not anchor and allow_unanchored:
        on_chain_match = None  # legitimately unanchored at issue time
    else:
        on_chain_match = False

    return {
        "ok": True if (on_chain_match is not False) else False,
        "signature_valid": True,
        "schema": payload.get("schema"),
        "lot_id": lot_id,
        "lot_number": payload.get("lot_number"),
        "bale_index": payload.get("bale_index"),
        "issued_at": payload.get("issued_at"),
        "anchor": anchor,
        "on_chain_match": on_chain_match,
    }


__all__ = [
    "PassportBundle",
    "issue_passport",
    "verify_passport_token",
]
