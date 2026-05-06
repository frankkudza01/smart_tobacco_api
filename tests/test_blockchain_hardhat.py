"""
Optional integration tests against a live Hardhat node.

Prerequisites:
  1. Terminal A: cd backend/hardhat && npm run node
  2. Terminal B: cd backend/hardhat && npm run deploy:local
  3. Export (contract address from deploy output):
       export INTEGRATE_HARDHAT=1
       export BLOCKCHAIN_CONTRACT_ADDRESS=0x...
       export BLOCKCHAIN_PRIVATE_KEY=0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80

Run:
  INTEGRATE_HARDHAT=1 BLOCKCHAIN_CONTRACT_ADDRESS=0x... pytest tests/test_blockchain_hardhat.py -v
"""
import os
import uuid

import pytest
from django.test import override_settings

pytestmark = pytest.mark.django_db


def _hardhat_configured() -> bool:
    return (
        os.environ.get("INTEGRATE_HARDHAT") == "1"
        and bool(os.environ.get("BLOCKCHAIN_CONTRACT_ADDRESS", "").strip())
        and bool(os.environ.get("BLOCKCHAIN_PRIVATE_KEY", "").strip())
    )


requires_hardhat = pytest.mark.skipif(
    not _hardhat_configured(),
    reason="INTEGRATE_HARDHAT=1 plus BLOCKCHAIN_CONTRACT_ADDRESS and BLOCKCHAIN_PRIVATE_KEY (see docstring)",
)


def _django_hardhat_overrides():
    return {
        "BLOCKCHAIN_ENABLED": True,
        "BLOCKCHAIN_PROVIDER_URL": os.environ.get("BLOCKCHAIN_PROVIDER_URL", "http://127.0.0.1:8545"),
        "BLOCKCHAIN_CHAIN_ID": int(os.environ.get("BLOCKCHAIN_CHAIN_ID", "31337")),
        "BLOCKCHAIN_CONTRACT_ADDRESS": os.environ["BLOCKCHAIN_CONTRACT_ADDRESS"].strip(),
        "BLOCKCHAIN_PRIVATE_KEY": os.environ["BLOCKCHAIN_PRIVATE_KEY"].strip(),
    }


@requires_hardhat
def test_web3_gateway_anchor_event_hash():
    from apps.blockchain.gateway import Web3BlockchainGateway

    with override_settings(**_django_hardhat_overrides()):
        gw = Web3BlockchainGateway()
        h = "a" * 64
        ref = str(uuid.uuid4())
        result = gw.anchor_hash(h, "trace_event", ref)

    assert result["status"] == "CONFIRMED"
    assert result["tx_hash"].startswith("0x")
    assert result["block_number"] is not None

    with override_settings(**_django_hardhat_overrides()):
        gw = Web3BlockchainGateway()
        v = gw.verify_anchor(result["tx_hash"])
    assert v.get("verified") is True


@requires_hardhat
def test_web3_gateway_anchor_document_hash():
    from apps.blockchain.gateway import Web3BlockchainGateway

    with override_settings(**_django_hardhat_overrides()):
        gw = Web3BlockchainGateway()
        h = "b" * 64
        ref = str(uuid.uuid4())
        result = gw.anchor_hash(h, "document", ref)

    assert result["status"] == "CONFIRMED"


def test_data_hash_to_bytes32_helper():
    from apps.blockchain.gateway import _data_hash_to_bytes32

    b = _data_hash_to_bytes32("c" * 64)
    assert len(b) == 32
    assert _data_hash_to_bytes32("0x" + "d" * 64) == bytes.fromhex("d" * 64)

    with pytest.raises(ValueError):
        _data_hash_to_bytes32("tooshort")
