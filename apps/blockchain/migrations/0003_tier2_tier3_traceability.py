import uuid

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("blockchain", "0002_merkle_anchor_batch"),
        ("lots", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # ---- BlockchainReceipt: reconciliation fields ----
        migrations.AddField(
            model_name="blockchainreceipt",
            name="last_reconciled_at",
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="blockchainreceipt",
            name="reconciliation_status",
            field=models.CharField(
                choices=[
                    ("UNKNOWN", "Unknown"),
                    ("OK", "On-chain matches"),
                    ("DRIFT", "On-chain disagrees"),
                    ("MISSING", "On-chain record missing"),
                    ("UNVERIFIABLE", "Unverifiable (RPC error / mock chain)"),
                ],
                db_index=True,
                default="UNKNOWN",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="blockchainreceipt",
            name="reconciliation_notes",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddIndex(
            model_name="blockchainreceipt",
            index=models.Index(
                fields=["reconciliation_status"],
                name="blockchain__reconci_5e1d3f_idx",
            ),
        ),
        # ---- UserSigningKey ----
        migrations.CreateModel(
            name="UserSigningKey",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("address", models.CharField(db_index=True, max_length=42, unique=True)),
                ("encrypted_private_key", models.BinaryField()),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=models.deletion.CASCADE,
                        related_name="signing_key",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "blockchain_user_signing_key",
                "ordering": ["-created_at"],
            },
        ),
        # ---- CustodyTransfer ----
        migrations.CreateModel(
            name="CustodyTransfer",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("from_address", models.CharField(max_length=42)),
                ("to_address", models.CharField(max_length=42)),
                ("weight_kg", models.DecimalField(decimal_places=3, max_digits=12)),
                ("transfer_timestamp", models.DateTimeField()),
                ("notes", models.CharField(blank=True, default="", max_length=255)),
                ("canonical_payload", models.JSONField(blank=True, default=dict)),
                ("payload_hash", models.CharField(db_index=True, max_length=64)),
                ("from_signature", models.CharField(blank=True, default="", max_length=132)),
                ("to_signature", models.CharField(blank=True, default="", max_length=132)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("PENDING_ACCEPT", "Pending acceptance by recipient"),
                            ("ACCEPTED_AWAITING_ANCHOR", "Accepted, awaiting anchor"),
                            ("ANCHORED", "Anchored on chain"),
                            ("DECLINED", "Declined by recipient"),
                            ("CANCELLED", "Cancelled by initiator"),
                        ],
                        db_index=True,
                        default="PENDING_ACCEPT",
                        max_length=30,
                    ),
                ),
                ("accepted_at", models.DateTimeField(blank=True, null=True)),
                ("anchored_at", models.DateTimeField(blank=True, null=True)),
                ("anchor_tx_hash", models.CharField(blank=True, db_index=True, default="", max_length=66)),
                (
                    "anchor_status",
                    models.CharField(
                        choices=[
                            ("PENDING", "Pending"),
                            ("SUBMITTED", "Submitted"),
                            ("CONFIRMED", "Confirmed"),
                            ("FAILED", "Failed"),
                        ],
                        default="PENDING",
                        max_length=20,
                    ),
                ),
                (
                    "lot",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="custody_transfers",
                        to="lots.lot",
                    ),
                ),
                (
                    "from_user",
                    models.ForeignKey(
                        null=True,
                        on_delete=models.deletion.SET_NULL,
                        related_name="custody_transfers_initiated",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "to_user",
                    models.ForeignKey(
                        null=True,
                        on_delete=models.deletion.SET_NULL,
                        related_name="custody_transfers_received",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "blockchain_custody_transfer",
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(
                        fields=["lot", "status"],
                        name="blockchain__lot_id_2c9e4b_idx",
                    ),
                ],
            },
        ),
        # ---- InspectionAttestation ----
        migrations.CreateModel(
            name="InspectionAttestation",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("inspector_address", models.CharField(blank=True, default="", max_length=42)),
                ("score", models.PositiveSmallIntegerField()),
                ("summary", models.CharField(blank=True, default="", max_length=255)),
                ("notes_uri", models.CharField(blank=True, default="", max_length=255)),
                ("data_hash", models.CharField(db_index=True, max_length=64)),
                ("inspected_at", models.DateTimeField()),
                ("anchor_tx_hash", models.CharField(blank=True, db_index=True, default="", max_length=66)),
                (
                    "anchor_status",
                    models.CharField(
                        choices=[
                            ("PENDING", "Pending"),
                            ("SUBMITTED", "Submitted"),
                            ("CONFIRMED", "Confirmed"),
                            ("FAILED", "Failed"),
                        ],
                        default="PENDING",
                        max_length=20,
                    ),
                ),
                (
                    "lot",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="inspection_attestations",
                        to="lots.lot",
                    ),
                ),
                (
                    "inspector",
                    models.ForeignKey(
                        null=True,
                        on_delete=models.deletion.SET_NULL,
                        related_name="inspection_attestations",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "blockchain_inspection_attestation",
                "ordering": ["-inspected_at"],
            },
        ),
        # ---- AnchorRevocation ----
        migrations.CreateModel(
            name="AnchorRevocation",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "reason_code",
                    models.CharField(
                        choices=[
                            ("FRAUD_SUSPECTED", "Fraud suspected"),
                            ("DUPLICATE", "Duplicate record"),
                            ("DATA_CORRECTION", "Data correction issued"),
                            ("DISPUTE", "Disputed by counter-party"),
                            ("OTHER", "Other"),
                        ],
                        default="OTHER",
                        max_length=30,
                    ),
                ),
                ("reason_text", models.TextField()),
                ("reason_hash", models.CharField(db_index=True, max_length=64)),
                ("anchor_tx_hash", models.CharField(blank=True, db_index=True, default="", max_length=66)),
                (
                    "anchor_status",
                    models.CharField(
                        choices=[
                            ("PENDING", "Pending"),
                            ("SUBMITTED", "Submitted"),
                            ("CONFIRMED", "Confirmed"),
                            ("FAILED", "Failed"),
                        ],
                        default="PENDING",
                        max_length=20,
                    ),
                ),
                (
                    "target_receipt",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="revocations",
                        to="blockchain.blockchainreceipt",
                    ),
                ),
                (
                    "revoker",
                    models.ForeignKey(
                        null=True,
                        on_delete=models.deletion.SET_NULL,
                        related_name="anchor_revocations",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "blockchain_anchor_revocation",
                "ordering": ["-created_at"],
            },
        ),
    ]
