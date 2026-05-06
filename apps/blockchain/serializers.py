from rest_framework import serializers

from apps.blockchain.models import (
    AnchorRevocation,
    BlockchainReceipt,
    CustodyTransfer,
    InspectionAttestation,
    MerkleAnchorBatch,
)


class BlockchainReceiptSerializer(serializers.ModelSerializer):
    class Meta:
        model = BlockchainReceipt
        fields = [
            "id", "reference_type", "reference_id",
            "tx_hash", "block_number", "chain_id",
            "contract_address", "method_name", "data_hash",
            "status", "gas_used",
            "created_at",
        ]


class AnchorVerifySerializer(serializers.Serializer):
    tx_hash = serializers.CharField(max_length=66)


class MerkleAnchorBatchListSerializer(serializers.ModelSerializer):
    """Compact list view — leaves omitted to keep responses small."""

    class Meta:
        model = MerkleAnchorBatch
        fields = [
            "id", "batch_type", "batch_label",
            "period_start", "period_end",
            "leaf_count", "merkle_root",
            "anchor_status", "tx_hash", "block_number",
            "chain_id", "contract_address", "gas_used",
            "created_at",
        ]


class MerkleAnchorBatchDetailSerializer(serializers.ModelSerializer):
    """Detail view including the ordered leaves (auditor-only via view perms)."""

    class Meta:
        model = MerkleAnchorBatch
        fields = [
            "id", "batch_type", "batch_label",
            "period_start", "period_end",
            "leaf_count", "merkle_root", "leaves_json",
            "anchor_status", "tx_hash", "block_number",
            "chain_id", "contract_address", "gas_used",
            "raw_receipt",
            "created_at", "updated_at",
        ]


# ---------------------------------------------------------------------------
# Tier 2 / Tier 3 serializers
# ---------------------------------------------------------------------------


class CustodyInitiateSerializer(serializers.Serializer):
    lot_id = serializers.UUIDField()
    to_user_id = serializers.UUIDField()
    weight_kg = serializers.DecimalField(max_digits=12, decimal_places=3)
    transfer_timestamp = serializers.DateTimeField(required=False)
    notes = serializers.CharField(required=False, allow_blank=True, max_length=255)


class CustodyTransferSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustodyTransfer
        fields = [
            "id", "lot", "from_user", "to_user",
            "from_address", "to_address",
            "weight_kg", "transfer_timestamp", "notes",
            "payload_hash", "from_signature", "to_signature",
            "status", "accepted_at", "anchored_at",
            "anchor_tx_hash", "anchor_status",
            "created_at",
        ]


class InspectionAttestSerializer(serializers.Serializer):
    lot_id = serializers.UUIDField()
    score = serializers.IntegerField(min_value=0, max_value=100)
    summary = serializers.CharField(required=False, allow_blank=True, max_length=255)
    notes_uri = serializers.CharField(required=False, allow_blank=True, max_length=255)
    inspected_at = serializers.DateTimeField(required=False)


class InspectionAttestationSerializer(serializers.ModelSerializer):
    class Meta:
        model = InspectionAttestation
        fields = [
            "id", "lot", "inspector", "inspector_address",
            "score", "summary", "notes_uri",
            "data_hash", "inspected_at",
            "anchor_tx_hash", "anchor_status",
            "created_at",
        ]


class AnchorRevokeSerializer(serializers.Serializer):
    target_receipt_id = serializers.UUIDField()
    reason_code = serializers.ChoiceField(choices=AnchorRevocation.REASON_CHOICES)
    reason_text = serializers.CharField(min_length=5, max_length=2000)


class AnchorRevocationSerializer(serializers.ModelSerializer):
    target_receipt_tx_hash = serializers.CharField(source="target_receipt.tx_hash", read_only=True)

    class Meta:
        model = AnchorRevocation
        fields = [
            "id", "target_receipt", "target_receipt_tx_hash",
            "revoker", "reason_code", "reason_text", "reason_hash",
            "anchor_tx_hash", "anchor_status",
            "created_at",
        ]


class PassportIssueSerializer(serializers.Serializer):
    lot_id = serializers.UUIDField()
    bale_index = serializers.IntegerField(required=False, min_value=0)


class PassportVerifySerializer(serializers.Serializer):
    token = serializers.CharField(min_length=10, max_length=8000)
