# Generated manually for Distinction dispute governance

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def backfill_dispute_org(apps, schema_editor):
    Dispute = apps.get_model("disputes", "Dispute")
    Lot = apps.get_model("lots", "Lot")
    Sale = apps.get_model("sales", "Sale")
    for d in Dispute.objects.all().iterator():
        org_id = None
        if d.lot_id:
            try:
                lot = Lot.objects.select_related("season__farm").get(pk=d.lot_id)
                org_id = lot.season.farm.organization_id
            except Exception:
                pass
        elif d.sale_id:
            try:
                sale = Sale.objects.select_related("lot__season__farm").get(pk=d.sale_id)
                org_id = sale.lot.season.farm.organization_id
            except Exception:
                pass
        if org_id:
            d.organization_id = org_id
            d.save(update_fields=["organization_id"])


class Migration(migrations.Migration):

    dependencies = [
        ("organizations", "0001_initial"),
        ("disputes", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="dispute",
            name="organization",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="disputes",
                to="organizations.organization",
            ),
        ),
        migrations.AddField(
            model_name="dispute",
            name="category",
            field=models.CharField(
                blank=True,
                choices=[
                    ("grading", "Grading"),
                    ("sale", "Sale"),
                    ("document", "Document"),
                    ("sequence", "Trace sequence"),
                ],
                db_index=True,
                default="",
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name="dispute",
            name="related_trace_event_ids",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="dispute",
            name="related_document_ids",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="dispute",
            name="related_anomaly_ids",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="dispute",
            name="opened_by_role",
            field=models.CharField(blank=True, db_index=True, default="", max_length=32),
        ),
        migrations.AddField(
            model_name="dispute",
            name="first_response_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="dispute",
            name="resolved_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="disputes_resolved",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.RunPython(backfill_dispute_org, migrations.RunPython.noop),
    ]
