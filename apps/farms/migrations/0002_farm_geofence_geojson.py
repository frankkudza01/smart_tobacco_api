from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("farms", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="farm",
            name="geofence_geojson",
            field=models.JSONField(blank=True, null=True),
        ),
    ]
