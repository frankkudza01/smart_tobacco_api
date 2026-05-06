"""
SHA-256 Merkle trees for batch anchoring.

Why Merkle batching matters for traceability
--------------------------------------------
Anchoring every TraceEvent or Document hash as its own on-chain transaction is
expensive (one tx per event) and produces no aggregate proof. Daily Merkle
batching:

* commits a **single root hash** to chain per batch (≈100× cheaper gas), and
* lets us produce an *inclusion proof* of size ``O(log n)`` for any single
  leaf so a regulator can verify a specific event was inside the day's batch
  *without* needing to download or trust the entire database.

Hashing convention
------------------
* Leaves are 32-byte SHA-256 digests (we accept hex strings, lowercase or 0x-prefixed).
* Internal nodes: ``sha256(left || right)`` over **raw 32-byte concatenation**
  (no extra delimiter). When a level has an odd number of nodes, the last node
  is duplicated (Bitcoin / OpenZeppelin convention).
* Empty tree → ``GENESIS_EMPTY_ROOT`` (sha256 of the empty byte string).
* Leaf order is significant — the proof carries the position index.

The verifier in ``apps.blockchain.verifier`` consumes proofs produced here and
can also run **standalone** (no Django imports), which is what the public
proof-bundle JSON relies on.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Iterable

GENESIS_EMPTY_ROOT = hashlib.sha256(b"").hexdigest()


def _normalise_hex(value: str) -> bytes:
    s = (value or "").strip().lower()
    if s.startswith("0x"):
        s = s[2:]
    if len(s) != 64:
        raise ValueError(f"merkle leaf must be a 64-char SHA-256 hex digest; got length {len(s)}")
    try:
        return bytes.fromhex(s)
    except ValueError as exc:  # pragma: no cover — bytes.fromhex is exhaustive
        raise ValueError(f"invalid hex in merkle leaf: {exc}") from exc


def _hash_pair(left: bytes, right: bytes) -> bytes:
    return hashlib.sha256(left + right).digest()


def compute_merkle_root(leaves_hex: Iterable[str]) -> str:
    """Return the Merkle root as 64-char lowercase hex.

    Empty input returns ``GENESIS_EMPTY_ROOT`` so callers can still anchor
    "zero events today" if they want a continuous daily attestation.
    """
    layer = [_normalise_hex(h) for h in leaves_hex]
    if not layer:
        return GENESIS_EMPTY_ROOT
    while len(layer) > 1:
        if len(layer) % 2 == 1:
            layer.append(layer[-1])  # duplicate last (Bitcoin convention)
        next_layer: list[bytes] = []
        for i in range(0, len(layer), 2):
            next_layer.append(_hash_pair(layer[i], layer[i + 1]))
        layer = next_layer
    return layer[0].hex()


@dataclass(frozen=True)
class MerkleProofStep:
    """One sibling hash plus the side it sits on (left/right)."""

    sibling_hex: str
    position: str  # "left" | "right"  (relative to the *current* node climbing up)


def compute_inclusion_proof(leaves_hex: list[str], index: int) -> list[MerkleProofStep]:
    """Return the inclusion proof for ``leaves_hex[index]`` against the same tree."""
    if index < 0 or index >= len(leaves_hex):
        raise IndexError(f"leaf index {index} out of range for {len(leaves_hex)} leaves")
    layer = [_normalise_hex(h) for h in leaves_hex]
    proof: list[MerkleProofStep] = []
    cur = index
    while len(layer) > 1:
        if len(layer) % 2 == 1:
            layer.append(layer[-1])
        if cur % 2 == 0:
            sibling = layer[cur + 1]
            proof.append(MerkleProofStep(sibling_hex=sibling.hex(), position="right"))
        else:
            sibling = layer[cur - 1]
            proof.append(MerkleProofStep(sibling_hex=sibling.hex(), position="left"))
        next_layer: list[bytes] = []
        for i in range(0, len(layer), 2):
            next_layer.append(_hash_pair(layer[i], layer[i + 1]))
        layer = next_layer
        cur //= 2
    return proof


def verify_inclusion_proof(
    leaf_hex: str,
    proof: list[MerkleProofStep] | list[dict],
    expected_root_hex: str,
) -> bool:
    """Re-derive the root from ``leaf_hex`` and ``proof`` and compare to ``expected_root_hex``.

    ``proof`` may be a list of ``MerkleProofStep`` objects or plain dicts of
    shape ``{"sibling_hex": "...", "position": "left"|"right"}`` so the JSON
    proof bundle round-trips cleanly.
    """
    cur = _normalise_hex(leaf_hex)
    for step in proof:
        if isinstance(step, MerkleProofStep):
            sibling_hex, position = step.sibling_hex, step.position
        else:
            sibling_hex = str(step.get("sibling_hex") or "")
            position = str(step.get("position") or "")
        sibling = _normalise_hex(sibling_hex)
        if position == "left":
            cur = _hash_pair(sibling, cur)
        elif position == "right":
            cur = _hash_pair(cur, sibling)
        else:
            return False
    expected = (expected_root_hex or "").strip().lower().removeprefix("0x")
    return cur.hex() == expected
