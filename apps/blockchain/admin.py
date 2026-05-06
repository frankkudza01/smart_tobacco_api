from django.contrib import admin

from apps.blockchain.models import (
    AnchorRevocation,
    BlockchainReceipt,
    CustodyTransfer,
    InspectionAttestation,
    MerkleAnchorBatch,
    UserSigningKey,
)


@admin.register(BlockchainReceipt)
class BlockchainReceiptAdmin(admin.ModelAdmin):
    list_display = (
        "tx_hash", "reference_type", "reference_id",
        "status", "reconciliation_status", "block_number", "created_at",
    )
    list_filter = ("status", "reconciliation_status", "reference_type", "chain_id")
    search_fields = ("tx_hash", "data_hash")
    readonly_fields = ("raw_receipt",)


@admin.register(MerkleAnchorBatch)
class MerkleAnchorBatchAdmin(admin.ModelAdmin):
    list_display = (
        "batch_label", "batch_type", "leaf_count",
        "anchor_status", "tx_hash", "block_number", "period_start",
    )
    list_filter = ("batch_type", "anchor_status", "chain_id")
    search_fields = ("batch_label", "merkle_root", "tx_hash")
    readonly_fields = ("leaves_json", "raw_receipt", "merkle_root")


@admin.register(UserSigningKey)
class UserSigningKeyAdmin(admin.ModelAdmin):
    list_display = ("user", "address", "created_at")
    search_fields = ("address", "user__email")
    readonly_fields = ("encrypted_private_key", "address")


@admin.register(CustodyTransfer)
class CustodyTransferAdmin(admin.ModelAdmin):
    list_display = (
        "id", "lot", "from_address", "to_address",
        "weight_kg", "status", "anchor_status", "anchor_tx_hash", "created_at",
    )
    list_filter = ("status", "anchor_status")
    search_fields = ("from_address", "to_address", "anchor_tx_hash", "payload_hash")
    readonly_fields = (
        "canonical_payload", "payload_hash",
        "from_signature", "to_signature",
    )


@admin.register(InspectionAttestation)
class InspectionAttestationAdmin(admin.ModelAdmin):
    list_display = (
        "id", "lot", "inspector_address", "score",
        "anchor_status", "anchor_tx_hash", "inspected_at",
    )
    list_filter = ("anchor_status",)
    search_fields = ("data_hash", "anchor_tx_hash", "inspector_address")
    readonly_fields = ("data_hash",)


@admin.register(AnchorRevocation)
class AnchorRevocationAdmin(admin.ModelAdmin):
    list_display = (
        "id", "target_receipt", "reason_code",
        "anchor_status", "anchor_tx_hash", "created_at",
    )
    list_filter = ("reason_code", "anchor_status")
    search_fields = ("reason_text", "reason_hash", "anchor_tx_hash")
    readonly_fields = ("reason_hash",)
