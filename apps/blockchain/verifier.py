"""
Standalone proof-bundle verifier.

This module deliberately has **no Django imports**. A regulator, buyer, or
external auditor can copy ``merkle.py`` + ``verifier.py`` into any Python 3.10+
environment and verify a proof bundle JSON produced by ``merkle_service``.

Usage::

    import json
    from apps.blockchain.verifier import verify_proof_bundle
    bundle = json.load(open("lot-XYZ.proof.json"))
    report = verify_proof_bundle(bundle)
    assert report["ok"]
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from apps.blockchain.merkle import verify_inclusion_proof


def _recompute_event_hash(canonical_payload: dict[str, Any]) -> str:
    """Mirror ``TraceEvent.compute_hash`` so the verifier can re-derive event hashes."""
    canonical = json.dumps(canonical_payload, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def verify_proof_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    """Verify every event in a proof bundle. Returns a structured report.

    For each event we check, in order:

    1. ``event_hash`` matches ``sha256(canonical_payload)``.
    2. The hash chain is intact (each ``prev_event_hash`` equals the previous
       event's ``event_hash``; the first event's prev must be 64 zeros).
    3. If the event has an ``anchor`` block, the Merkle inclusion proof
       re-derives the on-chain ``merkle_root``.
    """
    if bundle.get("schema") != "smart-tobacco.proof-bundle.v1":
        return {"ok": False, "error": "unsupported_schema", "schema": bundle.get("schema")}

    events = bundle.get("events") or []
    GENESIS = "0" * 64

    results: list[dict[str, Any]] = []
    expected_prev = GENESIS
    all_event_hashes_ok = True
    all_chain_ok = True
    all_merkle_ok = True

    for ev in events:
        canonical = ev.get("canonical_payload") or {}
        recomputed_hash = _recompute_event_hash(canonical)
        stored_hash = (ev.get("event_hash") or "").lower()
        hash_match = recomputed_hash == stored_hash
        if not hash_match:
            all_event_hashes_ok = False

        prev_hash = (ev.get("prev_event_hash") or "").lower() or GENESIS
        chain_match = prev_hash == expected_prev
        if not chain_match:
            all_chain_ok = False

        anchor = ev.get("anchor")
        merkle_match: bool | None = None
        if anchor:
            merkle_root = anchor.get("merkle_root") or ""
            proof = ev.get("merkle_proof") or []
            merkle_match = verify_inclusion_proof(stored_hash or recomputed_hash, proof, merkle_root)
            if not merkle_match:
                all_merkle_ok = False

        results.append(
            {
                "event_id": ev.get("event_id"),
                "event_type": ev.get("event_type"),
                "hash_match": hash_match,
                "chain_match": chain_match,
                "merkle_match": merkle_match,
                "anchor_tx_hash": (anchor or {}).get("tx_hash"),
            }
        )
        expected_prev = stored_hash or recomputed_hash

    return {
        "ok": all_event_hashes_ok and all_chain_ok and all_merkle_ok,
        "schema": bundle.get("schema"),
        "lot": bundle.get("lot"),
        "event_count": len(events),
        "all_event_hashes_match": all_event_hashes_ok,
        "chain_intact": all_chain_ok,
        "merkle_intact": all_merkle_ok,
        "events": results,
    }
