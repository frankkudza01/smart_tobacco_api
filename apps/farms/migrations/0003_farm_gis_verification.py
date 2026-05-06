# Generated manually for GIS verification workflow

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("farms", "0002_farm_geofence_geojson"),
    ]

    operations = [
        migrations.AddField(
            model_name="farm",
            name="gis_verification_notes",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="farm",
            name="gis_verification_status",
            field=models.CharField(
                choices=[
                    ("PENDING", "Pending review"),
                    ("VERIFIED", "Verified"),
                    ("REJECTED", "Rejected"),
                ],
                db_index=True,
                default="PENDING",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="farm",
            name="gis_verified_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="farm",
            name="gis_verified_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="gis_verified_farms",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
