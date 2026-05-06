"""Pure unit tests for the Merkle utility (no Django DB required)."""
from __future__ import annotations

import hashlib

import pytest

from apps.blockchain.merkle import (
    GENESIS_EMPTY_ROOT,
    compute_inclusion_proof,
    compute_merkle_root,
    verify_inclusion_proof,
)


def _h(payload: str) -> str:
    return hashlib.sha256(payload.encode()).hexdigest()


def test_empty_tree_returns_genesis_root():
    assert compute_merkle_root([]) == GENESIS_EMPTY_ROOT
    assert GENESIS_EMPTY_ROOT == hashlib.sha256(b"").hexdigest()


def test_single_leaf_root_is_the_leaf_itself():
    leaf = _h("only")
    assert compute_merkle_root([leaf]) == leaf


def test_two_leaf_root_matches_manual_pair_hash():
    a, b = _h("a"), _h("b")
    expected = hashlib.sha256(bytes.fromhex(a) + bytes.fromhex(b)).hexdigest()
    assert compute_merkle_root([a, b]) == expected


def test_inclusion_proof_round_trips_for_every_index():
    """For every leaf in trees of size 1..7, prove and verify inclusion."""
    for n in range(1, 8):
        leaves = [_h(f"leaf-{i}") for i in range(n)]
        root = compute_merkle_root(leaves)
        for idx, leaf in enumerate(leaves):
            proof = compute_inclusion_proof(leaves, idx)
            assert verify_inclusion_proof(leaf, proof, root) is True, (n, idx)


def test_proof_fails_when_leaf_is_tampered():
    leaves = [_h(f"leaf-{i}") for i in range(5)]
    root = compute_merkle_root(leaves)
    proof = compute_inclusion_proof(leaves, 2)
    tampered = _h("forged")
    assert verify_inclusion_proof(tampered, proof, root) is False


def test_proof_fails_when_root_is_tampered():
    leaves = [_h(f"leaf-{i}") for i in range(4)]
    root = compute_merkle_root(leaves)
    proof = compute_inclusion_proof(leaves, 0)
    fake_root = _h("malicious")
    assert verify_inclusion_proof(leaves[0], proof, fake_root) is False
    assert verify_inclusion_proof(leaves[0], proof, root) is True


def test_normaliser_accepts_0x_prefix_and_uppercase():
    leaves_lower = [_h(f"leaf-{i}") for i in range(3)]
    leaves_mixed = [("0x" + h.upper()) for h in leaves_lower]
    assert compute_merkle_root(leaves_mixed) == compute_merkle_root(leaves_lower)


def test_inclusion_proof_index_out_of_range():
    with pytest.raises(IndexError):
        compute_inclusion_proof([_h("only")], 5)


def test_proof_dict_form_is_accepted_by_verifier():
    """The JSON proof bundle stores steps as plain dicts; verifier must accept that shape."""
    leaves = [_h(f"leaf-{i}") for i in range(6)]
    root = compute_merkle_root(leaves)
    proof_objs = compute_inclusion_proof(leaves, 4)
    proof_dicts = [{"sibling_hex": p.sibling_hex, "position": p.position} for p in proof_objs]
    assert verify_inclusion_proof(leaves[4], proof_dicts, root) is True
