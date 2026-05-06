import uuid

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("blockchain", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="MerkleAnchorBatch",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "batch_type",
                    models.CharField(
                        choices=[
                            ("trace_events", "Trace events"),
                            ("documents", "Documents"),
                        ],
                        db_index=True,
                        default="trace_events",
                        max_length=30,
                    ),
                ),
                (
                    "batch_label",
                    models.CharField(
                        help_text=(
                            "Human-readable label (e.g. 'trace_events-2026-05-02'); also enforced unique on chain "
                            "via off-chain dedupe."
                        ),
                        max_length=80,
                        unique=True,
                    ),
                ),
                ("period_start", models.DateTimeField(db_index=True)),
                ("period_end", models.DateTimeField(db_index=True)),
                ("leaf_count", models.PositiveIntegerField(default=0)),
                ("merkle_root", models.CharField(db_index=True, max_length=64)),
                ("leaves_json", models.JSONField(blank=True, default=list)),
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
                ("tx_hash", models.CharField(blank=True, db_index=True, default="", max_length=66)),
                ("block_number", models.PositiveBigIntegerField(blank=True, null=True)),
                ("chain_id", models.PositiveIntegerField(default=1337)),
                ("contract_address", models.CharField(blank=True, default="", max_length=42)),
                ("gas_used", models.PositiveBigIntegerField(blank=True, null=True)),
                ("raw_receipt", models.JSONField(blank=True, default=dict)),
            ],
            options={
                "db_table": "blockchain_merkle_batch",
                "ordering": ["-period_start"],
                "indexes": [
                    models.Index(
                        fields=["batch_type", "period_start"],
                        name="blockchain__batch_t_3a6c50_idx",
                    ),
                ],
            },
        ),
    ]
