# Generated manually — global season architecture: denormalized farm on Lot.

import django.db.models.deletion
from django.db import migrations, models


def forwards_backfill_lot_farm(apps, schema_editor):
    Lot = apps.get_model("lots", "Lot")
    Season = apps.get_model("seasons", "Season")
    for lot in Lot.objects.select_related("season").iterator(chunk_size=500):
        if lot.season_id and getattr(lot.season, "farm_id", None):
            Lot.objects.filter(pk=lot.pk).update(farm_id=lot.season.farm_id)


def backwards_clear_lot_farm(apps, schema_editor):
    apps.get_model("lots", "Lot").objects.all().update(farm_id=None)


class Migration(migrations.Migration):

    dependencies = [
        ("lots", "0001_initial"),
        ("seasons", "0002_season_farmer_acceptance"),
    ]

    operations = [
        migrations.AddField(
            model_name="lot",
            name="farm",
            field=models.ForeignKey(
                null=True,
                blank=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="lots",
                to="farms.farm",
            ),
        ),
        migrations.RunPython(forwards_backfill_lot_farm, backwards_clear_lot_farm),
        migrations.AlterField(
            model_name="lot",
            name="farm",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="lots",
                to="farms.farm",
            ),
        ),
    ]
