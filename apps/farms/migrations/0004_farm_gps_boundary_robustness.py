from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("farms", "0003_farm_gis_verification"),
    ]

    operations = [
        migrations.AddField(
            model_name="farm",
            name="geofence_horizontal_accuracy_m",
            field=models.PositiveSmallIntegerField(
                blank=True,
                null=True,
                help_text="Device-reported horizontal accuracy (m) when the boundary/GPS was captured.",
            ),
        ),
        migrations.AddField(
            model_name="farm",
            name="boundary_check_tolerance_m",
            field=models.PositiveSmallIntegerField(
                default=25,
                help_text="Extra margin (m) for boundary checks to absorb GPS drift and map digitisation error.",
            ),
        ),
    ]
