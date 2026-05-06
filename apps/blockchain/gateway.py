"""
Blockchain gateway adapter pattern.
MockBlockchainGateway for local dev/testing.
Web3BlockchainGateway for real chain interaction (Hardhat, Anvil, testnets).
"""
import abc
import hashlib
import logging
import uuid

from django.conf import settings

from apps.blockchain.contract_abi import TOBACCO_TRACEABILITY_ABI

logger = logging.getLogger(__name__)


class BlockchainGateway(abc.ABC):
    @abc.abstractmethod
    def anchor_hash(self, data_hash: str, reference_type: str, reference_id: str) -> dict:
        """Anchor a hash on-chain. Returns tx metadata."""

    @abc.abstractmethod
    def verify_anchor(self, tx_hash: str) -> dict:
        """Verify an anchor transaction."""

    @abc.abstractmethod
    def get_receipt(self, tx_hash: str) -> dict:
        """Get transaction receipt."""

    @abc.abstractmethod
    def anchor_batch_root(
        self,
        merkle_root: str,
        batch_type: str,
        batch_label: str,
        leaf_count: int,
    ) -> dict:
        """Anchor a Merkle root on-chain via ``anchorBatchRoot``."""

    @abc.abstractmethod
    def attest_inspection(
        self,
        lot_id: str,
        data_hash: str,
        score: int,
        notes_uri: str,
    ) -> dict:
        """Emit an InspectionAttested event on-chain."""

    @abc.abstractmethod
    def record_custody_transfer(
        self,
        lot_id: str,
        from_address: str,
        to_address: str,
        payload_hash: str,
        weight_grams: int,
        timestamp_unix: int,
    ) -> dict:
        """Record an off-chain co-signed custody transfer; emit CustodyTransferred."""

    @abc.abstractmethod
    def revoke_anchor(
        self,
        original_anchor_id_hex: str,
        reason_hash: str,
    ) -> dict:
        """Attach a revocation to a prior anchor; emit AnchorRevoked."""


class MockBlockchainGateway(BlockchainGateway):
    """Local mock that simulates blockchain anchoring without a real chain."""

    def anchor_hash(self, data_hash: str, reference_type: str, reference_id: str) -> dict:
        fake_tx = "0x" + hashlib.sha256(
            f"{data_hash}{reference_id}{uuid.uuid4()}".encode()
        ).hexdigest()[:64]
        logger.info("MOCK anchor: hash=%s tx=%s", data_hash, fake_tx)
        return {
            "tx_hash": fake_tx,
            "block_number": 12345,
            "chain_id": 1337,
            "contract_address": "0x" + "0" * 40,
            "gas_used": 21000,
            "status": "CONFIRMED",
        }

    def verify_anchor(self, tx_hash: str) -> dict:
        return {"verified": True, "tx_hash": tx_hash, "status": "CONFIRMED"}

    def get_receipt(self, tx_hash: str) -> dict:
        return {"tx_hash": tx_hash, "status": "CONFIRMED", "block_number": 12345}

    def anchor_batch_root(
        self,
        merkle_root: str,
        batch_type: str,
        batch_label: str,
        leaf_count: int,
    ) -> dict:
        fake_tx = "0x" + hashlib.sha256(
            f"{merkle_root}{batch_type}{batch_label}{leaf_count}{uuid.uuid4()}".encode()
        ).hexdigest()[:64]
        logger.info(
            "MOCK anchor_batch_root: root=%s label=%s leaves=%d tx=%s",
            merkle_root, batch_label, leaf_count, fake_tx,
        )
        return {
            "tx_hash": fake_tx,
            "block_number": 12345,
            "chain_id": 1337,
            "contract_address": "0x" + "0" * 40,
            "gas_used": 50000,
            "status": "CONFIRMED",
            "method_name": "anchorBatchRoot",
        }

    def _mock_tx(self, payload: str, *, method: str, gas: int = 30000) -> dict:
        fake_tx = "0x" + hashlib.sha256(f"{payload}{uuid.uuid4()}".encode()).hexdigest()[:64]
        return {
            "tx_hash": fake_tx,
            "block_number": 12345,
            "chain_id": 1337,
            "contract_address": "0x" + "0" * 40,
            "gas_used": gas,
            "status": "CONFIRMED",
            "method_name": method,
        }

    def attest_inspection(
        self,
        lot_id: str,
        data_hash: str,
        score: int,
        notes_uri: str,
    ) -> dict:
        logger.info("MOCK attest_inspection: lot=%s score=%d", lot_id, score)
        return self._mock_tx(
            f"inspection|{lot_id}|{data_hash}|{score}",
            method="attestInspection",
            gas=45000,
        )

    def record_custody_transfer(
        self,
        lot_id: str,
        from_address: str,
        to_address: str,
        payload_hash: str,
        weight_grams: int,
        timestamp_unix: int,
    ) -> dict:
        logger.info(
            "MOCK record_custody_transfer: lot=%s %s -> %s",
            lot_id, from_address, to_address,
        )
        return self._mock_tx(
            f"custody|{lot_id}|{from_address}|{to_address}|{payload_hash}|{weight_grams}|{timestamp_unix}",
            method="recordCustodyTransfer",
            gas=70000,
        )

    def revoke_anchor(self, original_anchor_id_hex: str, reason_hash: str) -> dict:
        logger.info("MOCK revoke_anchor: anchor=%s", original_anchor_id_hex)
        return self._mock_tx(
            f"revoke|{original_anchor_id_hex}|{reason_hash}",
            method="revokeAnchor",
            gas=40000,
        )


def _data_hash_to_bytes32(data_hash: str) -> bytes:
    """Normalize SHA-256 hex (64 chars, optional 0x) to 32 bytes."""
    s = data_hash.strip()
    if s.startswith("0x"):
        s = s[2:]
    if len(s) != 64:
        raise ValueError(
            f"data_hash must be 64 hex characters (SHA-256); got length {len(s)}"
        )
    return bytes.fromhex(s)


class Web3BlockchainGateway(BlockchainGateway):
    """
    Web3.py gateway: calls TobaccoTraceability.anchorEventHash / anchorDocumentHash
    with proper ABI encoding (required for Hardhat and real networks).
    """

    def __init__(self):
        from web3 import Web3

        self.w3 = Web3(Web3.HTTPProvider(settings.BLOCKCHAIN_PROVIDER_URL))
        self.chain_id = settings.BLOCKCHAIN_CHAIN_ID
        self.private_key = (settings.BLOCKCHAIN_PRIVATE_KEY or "").strip()
        self.contract_address = (settings.BLOCKCHAIN_CONTRACT_ADDRESS or "").strip()

        if not self.private_key:
            raise ValueError("BLOCKCHAIN_PRIVATE_KEY is required when BLOCKCHAIN_ENABLED=True")
        if not self.contract_address or self.contract_address == "0x0000000000000000000000000000000000000000":
            raise ValueError(
                "BLOCKCHAIN_CONTRACT_ADDRESS must be set to the deployed TobaccoTraceability address"
            )

        if not self.w3.is_connected():
            raise ConnectionError(
                f"Cannot connect to BLOCKCHAIN_PROVIDER_URL={settings.BLOCKCHAIN_PROVIDER_URL}"
            )

        self._account = self.w3.eth.account.from_key(self.private_key)
        self._contract = self.w3.eth.contract(
            address=self.w3.to_checksum_address(self.contract_address),
            abi=TOBACCO_TRACEABILITY_ABI,
        )

    def _send_contract_fn(self, fn) -> dict:
        """Build, sign, send, and await a contract function call. Returns receipt dict."""
        tx = fn.build_transaction(
            {
                "from": self._account.address,
                "nonce": self.w3.eth.get_transaction_count(self._account.address),
                "chainId": self.chain_id,
            }
        )

        if "gas" not in tx or tx.get("gas") is None:
            tx["gas"] = int(self.w3.eth.estimate_gas(tx) * 1.2)

        # Never mix legacy gasPrice with EIP-1559 fee fields.
        is_dynamic_fee = (
            tx.get("type") == 2
            or tx.get("type") == "0x2"
            or "maxFeePerGas" in tx
            or "maxPriorityFeePerGas" in tx
        )

        if is_dynamic_fee:
            tx.pop("gasPrice", None)
            if "maxPriorityFeePerGas" not in tx:
                try:
                    tx["maxPriorityFeePerGas"] = self.w3.eth.max_priority_fee
                except Exception:
                    # Fallback for providers that do not support eth_maxPriorityFeePerGas.
                    tx["maxPriorityFeePerGas"] = self.w3.to_wei(2, "gwei")
            if "maxFeePerGas" not in tx:
                base_fee = self.w3.eth.gas_price or self.w3.to_wei(20, "gwei")
                tx["maxFeePerGas"] = int(base_fee * 2 + tx["maxPriorityFeePerGas"])
        else:
            if self.w3.eth.gas_price is not None:
                tx.setdefault("gasPrice", self.w3.eth.gas_price)

        signed = self.w3.eth.account.sign_transaction(tx, self.private_key)
        raw = getattr(signed, "raw_transaction", None) or getattr(signed, "rawTransaction", None)
        tx_hash = self.w3.eth.send_raw_transaction(raw)
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

        tx_hex = receipt.transactionHash.hex()
        if not tx_hex.startswith("0x"):
            tx_hex = "0x" + tx_hex

        return {
            "tx_hash": tx_hex,
            "block_number": receipt.blockNumber,
            "chain_id": self.chain_id,
            "contract_address": self.contract_address,
            "gas_used": receipt.gasUsed,
            "status": "CONFIRMED" if receipt.status == 1 else "FAILED",
        }

    def anchor_hash(self, data_hash: str, reference_type: str, reference_id: str) -> dict:
        h32 = _data_hash_to_bytes32(data_hash)
        ref_type = (reference_type or "").strip()
        ref_id = str(reference_id)

        if ref_type.lower() == "document":
            fn = self._contract.functions.anchorDocumentHash(h32, ref_id)
        else:
            fn = self._contract.functions.anchorEventHash(h32, ref_type, ref_id)

        return self._send_contract_fn(fn)

    def anchor_batch_root(
        self,
        merkle_root: str,
        batch_type: str,
        batch_label: str,
        leaf_count: int,
    ) -> dict:
        root32 = _data_hash_to_bytes32(merkle_root)
        fn = self._contract.functions.anchorBatchRoot(
            root32,
            (batch_type or "").strip() or "trace_events",
            (batch_label or "").strip(),
            int(leaf_count),
        )
        out = self._send_contract_fn(fn)
        out["method_name"] = "anchorBatchRoot"
        return out

    def attest_inspection(
        self,
        lot_id: str,
        data_hash: str,
        score: int,
        notes_uri: str,
    ) -> dict:
        if not (0 <= int(score) <= 100):
            raise ValueError("score must be between 0 and 100")
        h32 = _data_hash_to_bytes32(data_hash)
        fn = self._contract.functions.attestInspection(
            str(lot_id), h32, int(score), str(notes_uri or "")
        )
        out = self._send_contract_fn(fn)
        out["method_name"] = "attestInspection"
        return out

    def record_custody_transfer(
        self,
        lot_id: str,
        from_address: str,
        to_address: str,
        payload_hash: str,
        weight_grams: int,
        timestamp_unix: int,
    ) -> dict:
        h32 = _data_hash_to_bytes32(payload_hash)
        fn = self._contract.functions.recordCustodyTransfer(
            str(lot_id),
            self.w3.to_checksum_address(from_address),
            self.w3.to_checksum_address(to_address),
            h32,
            int(weight_grams),
            int(timestamp_unix),
        )
        out = self._send_contract_fn(fn)
        out["method_name"] = "recordCustodyTransfer"
        return out

    def revoke_anchor(self, original_anchor_id_hex: str, reason_hash: str) -> dict:
        original32 = _data_hash_to_bytes32(original_anchor_id_hex)
        reason32 = _data_hash_to_bytes32(reason_hash)
        fn = self._contract.functions.revokeAnchor(original32, reason32)
        out = self._send_contract_fn(fn)
        out["method_name"] = "revokeAnchor"
        return out

    def verify_anchor(self, tx_hash: str) -> dict:
        try:
            receipt = self.w3.eth.get_transaction_receipt(tx_hash)
            return {
                "verified": receipt.status == 1,
                "tx_hash": tx_hash,
                "block_number": receipt.blockNumber,
                "status": "CONFIRMED" if receipt.status == 1 else "FAILED",
            }
        except Exception as exc:
            return {"verified": False, "tx_hash": tx_hash, "error": str(exc)}

    def get_receipt(self, tx_hash: str) -> dict:
        receipt = self.w3.eth.get_transaction_receipt(tx_hash)
        return {
            "tx_hash": tx_hash,
            "block_number": receipt.blockNumber,
            "status": "CONFIRMED" if receipt.status == 1 else "FAILED",
            "gas_used": receipt.gasUsed,
        }


def get_blockchain_gateway() -> BlockchainGateway:
    if settings.BLOCKCHAIN_ENABLED:
        return Web3BlockchainGateway()
    return MockBlockchainGateway()
