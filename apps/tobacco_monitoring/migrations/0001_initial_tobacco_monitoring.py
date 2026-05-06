# Generated manually for tobacco_monitoring

import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("farms", "0002_farm_geofence_geojson"),
    ]

    operations = [
        migrations.CreateModel(
            name="TobaccoFieldPolygon",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("field_name", models.CharField(max_length=255)),
                ("crop_type", models.CharField(db_index=True, default="tobacco", max_length=64)),
                ("tobacco_class", models.CharField(blank=True, max_length=64)),
                ("planting_date", models.DateField(blank=True, null=True)),
                ("season", models.CharField(blank=True, db_index=True, max_length=32)),
                ("growth_stage", models.CharField(choices=[
                    ("pre_plant", "Pre-plant"),
                    ("transplant", "Transplant"),
                    ("vegetative", "Vegetative"),
                    ("flowering", "Flowering"),
                    ("maturity", "Maturity"),
                    ("harvest", "Harvest"),
                    ("other", "Other"),
                ], default="vegetative", max_length=32)),
                ("area_hectares", models.DecimalField(blank=True, decimal_places=4, help_text="Declared or computed area in hectares.", max_digits=12, null=True)),
                ("province", models.CharField(db_index=True, max_length=128)),
                ("district", models.CharField(blank=True, db_index=True, max_length=128)),
                ("ward", models.CharField(blank=True, max_length=128)),
                ("monitoring_status", models.CharField(choices=[
                    ("pending", "Pending registration"),
                    ("registered", "Registered with provider"),
                    ("active", "Actively monitored"),
                    ("paused", "Paused"),
                    ("error", "Error"),
                ], db_index=True, default="pending", max_length=32)),
                ("whatsapp_phone_e164", models.CharField(blank=True, help_text="E.164 phone for WhatsApp alerts (e.g. +263771234567).", max_length=32)),
                ("agromonitoring_poly_id", models.CharField(blank=True, db_index=True, help_text="Polygon id returned by AgroMonitoring.", max_length=64)),
                ("last_imagery_check_at", models.DateTimeField(blank=True, null=True)),
                ("last_successful_imagery_date", models.DateField(blank=True, null=True)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("geometry_geojson", models.JSONField(help_text="GeoJSON Polygon or MultiPolygon.")),
                ("raw_registration_payload", models.JSONField(blank=True, null=True)),
                ("default_alert_language", models.CharField(default="en", max_length=10)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_tobacco_polygons", to=settings.AUTH_USER_MODEL)),
                ("farm", models.ForeignKey(help_text="Farm this polygon belongs to.", on_delete=django.db.models.deletion.CASCADE, related_name="tobacco_field_polygons", to="farms.farm")),
            ],
            options={
                "ordering": ["-created_at"],
                "verbose_name": "Tobacco field polygon",
                "verbose_name_plural": "Tobacco field polygons",
            },
        ),
        migrations.CreateModel(
            name="SatelliteImageryRecord",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("acquisition_date", models.DateField(db_index=True)),
                ("source", models.CharField(default="sentinel-2", max_length=64)),
                ("cloud_cover", models.FloatField(blank=True, null=True)),
                ("scene_id", models.CharField(blank=True, max_length=256)),
                ("raw_payload", models.JSONField(blank=True, null=True)),
                ("processed", models.BooleanField(db_index=True, default=False)),
                ("idempotency_key", models.CharField(max_length=256, unique=True)),
                ("polygon", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="imagery_records", to="tobacco_monitoring.tobaccofieldpolygon")),
            ],
            options={
                "ordering": ["-acquisition_date"],
                "verbose_name": "Satellite imagery record",
                "verbose_name_plural": "Satellite imagery records",
            },
        ),
        migrations.CreateModel(
            name="PolygonObservation",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("observation_date", models.DateField(db_index=True)),
                ("metric_type", models.CharField(choices=[
                    ("ndvi", "NDVI"),
                    ("ndwi", "NDWI (moisture proxy)"),
                    ("soil_moisture", "Soil moisture"),
                    ("cloud_cover", "Cloud cover"),
                ], db_index=True, max_length=32)),
                ("metric_value", models.FloatField()),
                ("source", models.CharField(default="agromonitoring", max_length=64)),
                ("scene_id", models.CharField(blank=True, max_length=256)),
                ("cloud_cover", models.FloatField(blank=True, null=True)),
                ("raw_payload", models.JSONField(blank=True, null=True)),
                ("polygon", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="observations", to="tobacco_monitoring.tobaccofieldpolygon")),
            ],
            options={
                "ordering": ["-observation_date"],
                "verbose_name": "Polygon observation",
                "verbose_name_plural": "Polygon observations",
            },
        ),
        migrations.CreateModel(
            name="CropStressEvent",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("event_type", models.CharField(choices=[
                    ("ndvi_drop", "NDVI drop stress"),
                    ("moisture_stress", "Moisture stress"),
                    ("planting_gap", "Planting / establishment gap"),
                    ("other", "Other"),
                ], max_length=32)),
                ("severity", models.CharField(choices=[
                    ("low", "Low"),
                    ("medium", "Medium"),
                    ("high", "High"),
                ], max_length=16)),
                ("observation_date", models.DateField(db_index=True)),
                ("previous_ndvi", models.FloatField(blank=True, null=True)),
                ("current_ndvi", models.FloatField(blank=True, null=True)),
                ("percentage_change", models.FloatField(blank=True, null=True)),
                ("growth_stage", models.CharField(blank=True, max_length=32)),
                ("season", models.CharField(blank=True, max_length=32)),
                ("province", models.CharField(blank=True, max_length=128)),
                ("message_template_key", models.CharField(default="ndvi_drop", max_length=64)),
                ("localized_message", models.TextField(blank=True)),
                ("status", models.CharField(choices=[
                    ("pending", "Pending"),
                    ("queued", "Queued"),
                    ("sent", "Sent"),
                    ("failed", "Failed"),
                    ("acknowledged", "Acknowledged"),
                ], db_index=True, default="pending", max_length=16)),
                ("raw_reason", models.TextField(blank=True)),
                ("dedupe_key", models.CharField(max_length=256, unique=True)),
                ("polygon", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="stress_events", to="tobacco_monitoring.tobaccofieldpolygon")),
            ],
            options={
                "ordering": ["-created_at"],
                "verbose_name": "Crop stress event",
                "verbose_name_plural": "Crop stress events",
            },
        ),
        migrations.CreateModel(
            name="WhatsAppDeliveryLog",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("to_phone_e164", models.CharField(max_length=32)),
                ("attempt_number", models.PositiveSmallIntegerField(default=1)),
                ("status", models.CharField(choices=[
                    ("pending", "Pending"),
                    ("queued", "Queued"),
                    ("sent", "Sent"),
                    ("failed", "Failed"),
                    ("acknowledged", "Acknowledged"),
                ], max_length=16)),
                ("provider_message_id", models.CharField(blank=True, max_length=128)),
                ("error_code", models.CharField(blank=True, max_length=64)),
                ("error_body", models.TextField(blank=True)),
                ("raw_request", models.JSONField(blank=True, null=True)),
                ("raw_response", models.JSONField(blank=True, null=True)),
                ("stress_event", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="whatsapp_deliveries", to="tobacco_monitoring.cropstressevent")),
            ],
            options={
                "ordering": ["-created_at"],
                "verbose_name": "WhatsApp delivery log",
                "verbose_name_plural": "WhatsApp delivery logs",
            },
        ),
        migrations.CreateModel(
            name="PlantingVerificationRecord",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("assessed_at", models.DateTimeField(auto_now_add=True)),
                ("status", models.CharField(choices=[
                    ("not_detected", "Not detected"),
                    ("partially_established", "Partially established"),
                    ("established", "Established"),
                    ("verified_planted", "Verified planted"),
                ], db_index=True, max_length=32)),
                ("confidence", models.FloatField(blank=True, help_text="0–1 optional confidence.", null=True)),
                ("notes", models.TextField(blank=True)),
                ("assessed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="planting_verifications_done", to=settings.AUTH_USER_MODEL)),
                ("polygon", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="planting_verifications", to="tobacco_monitoring.tobaccofieldpolygon")),
            ],
            options={
                "ordering": ["-assessed_at"],
                "verbose_name": "Planting verification record",
                "verbose_name_plural": "Planting verification records",
            },
        ),
        migrations.AddIndex(
            model_name="tobaccofieldpolygon",
            index=models.Index(fields=["farm", "is_active"], name="tobacco_mon_farm_id_7a8b2c_idx"),
        ),
        migrations.AddIndex(
            model_name="tobaccofieldpolygon",
            index=models.Index(fields=["province", "district"], name="tobacco_mon_provinc_9d0e1f_idx"),
        ),
        migrations.AddConstraint(
            model_name="polygonobservation",
            constraint=models.UniqueConstraint(fields=("polygon", "observation_date", "metric_type"), name="uniq_polygon_observation_metric"),
        ),
    ]
