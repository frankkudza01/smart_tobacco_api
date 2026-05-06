from django.conf import settings
from django.db import models

from apps.common.enums import BlockchainAnchorStatus
from apps.common.models import BaseModel


class ReconciliationStatus(models.TextChoices):
    UNKNOWN = "UNKNOWN", "Unknown"
    OK = "OK", "On-chain matches"
    DRIFT = "DRIFT", "On-chain disagrees"
    MISSING = "MISSING", "On-chain record missing"
    UNVERIFIABLE = "UNVERIFIABLE", "Unverifiable (RPC error / mock chain)"


class CustodyStatus(models.TextChoices):
    PENDING_ACCEPT = "PENDING_ACCEPT", "Pending acceptance by recipient"
    ACCEPTED_AWAITING_ANCHOR = "ACCEPTED_AWAITING_ANCHOR", "Accepted, awaiting anchor"
    ANCHORED = "ANCHORED", "Anchored on chain"
    DECLINED = "DECLINED", "Declined by recipient"
    CANCELLED = "CANCELLED", "Cancelled by initiator"


class BlockchainReceipt(BaseModel):
    reference_type = models.CharField(max_length=50, db_index=True)
    reference_id = models.UUIDField(db_index=True)
    tx_hash = models.CharField(max_length=66, unique=True, db_index=True)
    block_number = models.PositiveBigIntegerField(null=True, blank=True)
    chain_id = models.PositiveIntegerField(default=1337)
    contract_address = models.CharField(max_length=42, blank=True, default="")
    method_name = models.CharField(max_length=100, blank=True, default="")
    data_hash = models.CharField(max_length=64, blank=True, default="")
    status = models.CharField(
        max_length=20,
        choices=BlockchainAnchorStatus.choices,
        default=BlockchainAnchorStatus.SUBMITTED,
    )
    gas_used = models.PositiveBigIntegerField(null=True, blank=True)
    raw_receipt = models.JSONField(default=dict, blank=True)

    # Reconciliation: re-read on-chain state to detect drift / chain reorgs.
    last_reconciled_at = models.DateTimeField(null=True, blank=True, db_index=True)
    reconciliation_status = models.CharField(
        max_length=20,
        choices=ReconciliationStatus.choices,
        default=ReconciliationStatus.UNKNOWN,
        db_index=True,
    )
    reconciliation_notes = models.TextField(blank=True, default="")

    class Meta:
        db_table = "blockchain_receipt"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["reference_type", "reference_id"]),
            models.Index(fields=["reconciliation_status"]),
        ]

    def __str__(self):
        return f"TX {self.tx_hash[:10]}... for {self.reference_type}:{self.reference_id}"


class UserSigningKey(BaseModel):
    """Per-user ECDSA keypair used for off-chain co-signing of custody transfers.

    Private key is encrypted with Fernet (key derived from ``settings.SECRET_KEY``)
    so it never lives in plaintext at rest. The signing address is derived from
    the public key and is what the smart contract's ``CustodyTransferred`` event
    records.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="signing_key",
    )
    address = models.CharField(max_length=42, db_index=True, unique=True)
    encrypted_private_key = models.BinaryField()

    class Meta:
        db_table = "blockchain_user_signing_key"
        ordering = ["-created_at"]

    def __str__(self):
        return f"SigningKey for {self.user_id} = {self.address}"


class CustodyTransfer(BaseModel):
    """Co-signed custody transfer record (off-chain proof + on-chain anchor)."""

    lot = models.ForeignKey(
        "lots.Lot",
        on_delete=models.CASCADE,
        related_name="custody_transfers",
    )
    from_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="custody_transfers_initiated",
    )
    to_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="custody_transfers_received",
    )
    from_address = models.CharField(max_length=42)
    to_address = models.CharField(max_length=42)
    weight_kg = models.DecimalField(max_digits=12, decimal_places=3)
    transfer_timestamp = models.DateTimeField()
    notes = models.CharField(max_length=255, blank=True, default="")

    canonical_payload = models.JSONField(default=dict, blank=True)
    payload_hash = models.CharField(max_length=64, db_index=True)
    from_signature = models.CharField(max_length=132, blank=True, default="")
    to_signature = models.CharField(max_length=132, blank=True, default="")

    status = models.CharField(
        max_length=30,
        choices=CustodyStatus.choices,
        default=CustodyStatus.PENDING_ACCEPT,
        db_index=True,
    )
    accepted_at = models.DateTimeField(null=True, blank=True)
    anchored_at = models.DateTimeField(null=True, blank=True)

    anchor_tx_hash = models.CharField(max_length=66, blank=True, default="", db_index=True)
    anchor_status = models.CharField(
        max_length=20,
        choices=BlockchainAnchorStatus.choices,
        default=BlockchainAnchorStatus.PENDING,
    )

    class Meta:
        db_table = "blockchain_custody_transfer"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["lot", "status"]),
        ]

    def __str__(self):
        return f"Custody {self.from_address[:8]}->{self.to_address[:8]} on {self.lot_id}"


class InspectionAttestation(BaseModel):
    """Off-chain record of a TIMB / regulator inspection attestation.

    Mirrors the on-chain ``InspectionAttested`` event for fast querying without
    re-reading the chain.
    """

    lot = models.ForeignKey(
        "lots.Lot",
        on_delete=models.CASCADE,
        related_name="inspection_attestations",
    )
    inspector = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="inspection_attestations",
    )
    inspector_address = models.CharField(max_length=42, blank=True, default="")
    score = models.PositiveSmallIntegerField()  # 0..100
    summary = models.CharField(max_length=255, blank=True, default="")
    notes_uri = models.CharField(max_length=255, blank=True, default="")
    data_hash = models.CharField(max_length=64, db_index=True)
    inspected_at = models.DateTimeField()

    anchor_tx_hash = models.CharField(max_length=66, blank=True, default="", db_index=True)
    anchor_status = models.CharField(
        max_length=20,
        choices=BlockchainAnchorStatus.choices,
        default=BlockchainAnchorStatus.PENDING,
    )

    class Meta:
        db_table = "blockchain_inspection_attestation"
        ordering = ["-inspected_at"]

    def __str__(self):
        return f"Inspection lot={self.lot_id} score={self.score}"


class AnchorRevocation(BaseModel):
    """Auditor-issued revocation/dispute attestation for a previously anchored item.

    The original anchor remains on-chain; the revocation is an additive
    counter-attestation so the full audit trail is preserved.
    """

    REASON_CHOICES = [
        ("FRAUD_SUSPECTED", "Fraud suspected"),
        ("DUPLICATE", "Duplicate record"),
        ("DATA_CORRECTION", "Data correction issued"),
        ("DISPUTE", "Disputed by counter-party"),
        ("OTHER", "Other"),
    ]

    target_receipt = models.ForeignKey(
        BlockchainReceipt,
        on_delete=models.CASCADE,
        related_name="revocations",
    )
    revoker = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="anchor_revocations",
    )
    reason_code = models.CharField(max_length=30, choices=REASON_CHOICES, default="OTHER")
    reason_text = models.TextField()
    reason_hash = models.CharField(max_length=64, db_index=True)

    anchor_tx_hash = models.CharField(max_length=66, blank=True, default="", db_index=True)
    anchor_status = models.CharField(
        max_length=20,
        choices=BlockchainAnchorStatus.choices,
        default=BlockchainAnchorStatus.PENDING,
    )

    class Meta:
        db_table = "blockchain_anchor_revocation"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Revocation {self.reason_code} on {self.target_receipt_id}"


class MerkleAnchorBatch(BaseModel):
    """Daily Merkle root anchored on-chain.

    Each row is the off-chain record of one ``anchorBatchRoot`` call:

    * ``leaves_json`` is the **ordered** list of canonical leaves
      (``[{"reference_type": ..., "reference_id": ..., "leaf_hash": "..."}]``).
      Order is what makes the inclusion proofs reproducible — never re-sort it.
    * ``merkle_root`` is the SHA-256 root committed on-chain.
    * ``tx_hash`` ties the batch to its on-chain transaction so any auditor
      can verify ``contract.verifyBatchRoot(batchId).merkleRoot == merkle_root``.
    """

    BATCH_TYPE_TRACE_EVENTS = "trace_events"
    BATCH_TYPE_DOCUMENTS = "documents"

    BATCH_TYPE_CHOICES = [
        (BATCH_TYPE_TRACE_EVENTS, "Trace events"),
        (BATCH_TYPE_DOCUMENTS, "Documents"),
    ]

    batch_type = models.CharField(
        max_length=30,
        choices=BATCH_TYPE_CHOICES,
        default=BATCH_TYPE_TRACE_EVENTS,
        db_index=True,
    )
    batch_label = models.CharField(
        max_length=80,
        unique=True,
        help_text="Human-readable label (e.g. 'trace_events-2026-05-02'); also enforced unique on chain via off-chain dedupe.",
    )
    period_start = models.DateTimeField(db_index=True)
    period_end = models.DateTimeField(db_index=True)
    leaf_count = models.PositiveIntegerField(default=0)
    merkle_root = models.CharField(max_length=64, db_index=True)
    leaves_json = models.JSONField(default=list, blank=True)
    anchor_status = models.CharField(
        max_length=20,
        choices=BlockchainAnchorStatus.choices,
        default=BlockchainAnchorStatus.PENDING,
    )
    tx_hash = models.CharField(max_length=66, blank=True, default="", db_index=True)
    block_number = models.PositiveBigIntegerField(null=True, blank=True)
    chain_id = models.PositiveIntegerField(default=1337)
    contract_address = models.CharField(max_length=42, blank=True, default="")
    gas_used = models.PositiveBigIntegerField(null=True, blank=True)
    raw_receipt = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "blockchain_merkle_batch"
        ordering = ["-period_start"]
        indexes = [
            models.Index(fields=["batch_type", "period_start"]),
        ]

    def __str__(self):
        return f"MerkleBatch {self.batch_label} ({self.leaf_count} leaves)"
