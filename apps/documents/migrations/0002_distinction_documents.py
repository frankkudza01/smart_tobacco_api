# Generated manually for Distinction document workflow

import uuid

import django.db.models.deletion
from django.db import migrations, models


def backfill_document_org_and_state(apps, schema_editor):
    Document = apps.get_model("documents", "Document")
    Lot = apps.get_model("lots", "Lot")
    for doc in Document.objects.filter(organization__isnull=True).iterator():
        if not doc.lot_id:
            continue
        try:
            lot = Lot.objects.select_related("season__farm").get(pk=doc.lot_id)
            oid = lot.season.farm.organization_id
            if oid:
                doc.organization_id = oid
                vs = "HASHED" if doc.sha256_hash else "UPLOADED"
                doc.verification_state = vs
                doc.save(update_fields=["organization_id", "verification_state"])
        except Exception:
            pass


class Migration(migrations.Migration):

    dependencies = [
        ("organizations", "0001_initial"),
        ("documents", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="document",
            name="organization",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="documents",
                to="organizations.organization",
            ),
        ),
        migrations.AddField(
            model_name="document",
            name="storage_pointer_hash",
            field=models.CharField(blank=True, db_index=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="document",
            name="verification_state",
            field=models.CharField(
                choices=[
                    ("UPLOADED", "Uploaded"),
                    ("HASHED", "Hashed"),
                    ("ANCHORED", "Anchored"),
                    ("VERIFIED", "Verified"),
                ],
                db_index=True,
                default="UPLOADED",
                max_length=20,
            ),
        ),
        migrations.CreateModel(
            name="DocumentFingerprint",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("extracted_text_redacted", models.TextField(blank=True, default="")),
                ("embedding_json", models.JSONField(blank=True, default=list)),
                ("key_fields_json", models.JSONField(blank=True, default=dict)),
                (
                    "document",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="fingerprint",
                        to="documents.document",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="document_fingerprints",
                        to="organizations.organization",
                    ),
                ),
            ],
            options={
                "db_table": "documents_document_fingerprint",
            },
        ),
        migrations.AddIndex(
            model_name="documentfingerprint",
            index=models.Index(fields=["organization", "document"], name="documents_d_organiz_idx"),
        ),
        migrations.RunPython(backfill_document_org_and_state, migrations.RunPython.noop),
    ]
