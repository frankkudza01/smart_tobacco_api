"""
Tobacco field satellite monitoring models.

Geometry is stored as GeoJSON in JSONField until PostGIS/GeoDjango is enabled.
"""

from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import BaseModel
from apps.farms.models import Farm


def _validate_geojson_polygon(data: dict) -> None:
    if not isinstance(data, dict):
        raise ValidationError(_("Geometry must be a GeoJSON object."))
    t = data.get("type")
    if t not in ("Polygon", "MultiPolygon"):
        raise ValidationError(_("Geometry type must be Polygon or MultiPolygon."))
    coords = data.get("coordinates")
    if not coords:
        raise ValidationError(_("Missing coordinates."))


class MonitoringStatus(models.TextChoices):
    PENDING = "pending", _("Pending registration")
    REGISTERED = "registered", _("Registered with provider")
    ACTIVE = "active", _("Actively monitored")
    PAUSED = "paused", _("Paused")
    ERROR = "error", _("Error")


class GrowthStage(models.TextChoices):
    PRE_PLANT = "pre_plant", _("Pre-plant")
    TRANSPLANT = "transplant", _("Transplant")
    VEGETATIVE = "vegetative", _("Vegetative")
    FLOWERING = "flowering", _("Flowering")
    MATURITY = "maturity", _("Maturity")
    HARVEST = "harvest", _("Harvest")
    OTHER = "other", _("Other")


class PlantingVerificationStatus(models.TextChoices):
    NOT_DETECTED = "not_detected", _("Not detected")
    PARTIALLY_ESTABLISHED = "partially_established", _("Partially established")
    ESTABLISHED = "established", _("Established")
    VERIFIED_PLANTED = "verified_planted", _("Verified planted")


class MetricType(models.TextChoices):
    NDVI = "ndvi", _("NDVI")
    NDWI = "ndwi", _("NDWI (moisture proxy)")
    SOIL_MOISTURE = "soil_moisture", _("Soil moisture")
    CLOUD_COVER = "cloud_cover", _("Cloud cover")


class CropStressEventType(models.TextChoices):
    NDVI_DROP = "ndvi_drop", _("NDVI drop stress")
    MOISTURE_STRESS = "moisture_stress", _("Moisture stress")
    PLANTING_GAP = "planting_gap", _("Planting / establishment gap")
    OTHER = "other", _("Other")


class StressSeverity(models.TextChoices):
    LOW = "low", _("Low")
    MEDIUM = "medium", _("Medium")
    HIGH = "high", _("High")


class AlertDeliveryStatus(models.TextChoices):
    PENDING = "pending", _("Pending")
    QUEUED = "queued", _("Queued")
    SENT = "sent", _("Sent")
    FAILED = "failed", _("Failed")
    ACKNOWLEDGED = "acknowledged", _("Acknowledged")


class TobaccoFieldPolygon(BaseModel):
    """
    Registered tobacco (or other crop) field boundary for satellite monitoring.
    """

    farm = models.ForeignKey(
        Farm,
        on_delete=models.CASCADE,
        related_name="tobacco_field_polygons",
        help_text=_("Farm this polygon belongs to."),
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_tobacco_polygons",
    )
    field_name = models.CharField(max_length=255)
    crop_type = models.CharField(
        max_length=64,
        default="tobacco",
        db_index=True,
        help_text=_("Crop type; default tobacco."),
    )
    tobacco_class = models.CharField(max_length=64, blank=True)
    planting_date = models.DateField(null=True, blank=True)
    season = models.CharField(max_length=32, blank=True, db_index=True)
    growth_stage = models.CharField(
        max_length=32,
        choices=GrowthStage.choices,
        default=GrowthStage.VEGETATIVE,
    )
    area_hectares = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        null=True,
        blank=True,
        help_text=_("Declared or computed area in hectares."),
    )
    province = models.CharField(max_length=128, db_index=True)
    district = models.CharField(max_length=128, blank=True, db_index=True)
    ward = models.CharField(max_length=128, blank=True)
    monitoring_status = models.CharField(
        max_length=32,
        choices=MonitoringStatus.choices,
        default=MonitoringStatus.PENDING,
        db_index=True,
    )
    whatsapp_phone_e164 = models.CharField(
        max_length=32,
        blank=True,
        help_text=_("E.164 phone for WhatsApp alerts (e.g. +263771234567)."),
    )
    agromonitoring_poly_id = models.CharField(
        max_length=64,
        blank=True,
        db_index=True,
        help_text=_("Polygon id returned by AgroMonitoring."),
    )
    last_imagery_check_at = models.DateTimeField(null=True, blank=True)
    last_successful_imagery_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    geometry_geojson = models.JSONField(help_text=_("GeoJSON Polygon or MultiPolygon."))
    raw_registration_payload = models.JSONField(null=True, blank=True)
    default_alert_language = models.CharField(max_length=10, default="en")

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("Tobacco field polygon")
        verbose_name_plural = _("Tobacco field polygons")
        indexes = [
            models.Index(fields=["farm", "is_active"]),
            models.Index(fields=["province", "district"]),
        ]

    def __str__(self) -> str:
        return f"{self.field_name} ({self.province})"

    def clean(self) -> None:
        super().clean()
        _validate_geojson_polygon(self.geometry_geojson)


class SatelliteImageryRecord(BaseModel):
    """One satellite scene / acquisition tied to a polygon."""

    polygon = models.ForeignKey(
        TobaccoFieldPolygon,
        on_delete=models.CASCADE,
        related_name="imagery_records",
    )
    acquisition_date = models.DateField(db_index=True)
    source = models.CharField(max_length=64, default="sentinel-2")
    cloud_cover = models.FloatField(null=True, blank=True)
    scene_id = models.CharField(max_length=256, blank=True)
    raw_payload = models.JSONField(null=True, blank=True)
    processed = models.BooleanField(default=False, db_index=True)
    idempotency_key = models.CharField(max_length=256, unique=True)

    class Meta:
        ordering = ["-acquisition_date"]
        verbose_name = _("Satellite imagery record")
        verbose_name_plural = _("Satellite imagery records")

    def __str__(self) -> str:
        return f"{self.polygon_id} {self.acquisition_date}"


class PolygonObservation(BaseModel):
    """Time-series metric per polygon and acquisition date."""

    polygon = models.ForeignKey(
        TobaccoFieldPolygon,
        on_delete=models.CASCADE,
        related_name="observations",
    )
    observation_date = models.DateField(db_index=True)
    metric_type = models.CharField(max_length=32, choices=MetricType.choices, db_index=True)
    metric_value = models.FloatField()
    source = models.CharField(max_length=64, default="agromonitoring")
    scene_id = models.CharField(max_length=256, blank=True)
    cloud_cover = models.FloatField(null=True, blank=True)
    raw_payload = models.JSONField(null=True, blank=True)

    class Meta:
        ordering = ["-observation_date"]
        constraints = [
            models.UniqueConstraint(
                fields=["polygon", "observation_date", "metric_type"],
                name="uniq_polygon_observation_metric",
            ),
        ]
        verbose_name = _("Polygon observation")
        verbose_name_plural = _("Polygon observations")


class CropStressEvent(BaseModel):
    """Detected crop stress / monitoring alert."""

    polygon = models.ForeignKey(
        TobaccoFieldPolygon,
        on_delete=models.CASCADE,
        related_name="stress_events",
    )
    event_type = models.CharField(max_length=32, choices=CropStressEventType.choices)
    severity = models.CharField(max_length=16, choices=StressSeverity.choices)
    observation_date = models.DateField(db_index=True)
    previous_ndvi = models.FloatField(null=True, blank=True)
    current_ndvi = models.FloatField(null=True, blank=True)
    percentage_change = models.FloatField(null=True, blank=True)
    growth_stage = models.CharField(max_length=32, blank=True)
    season = models.CharField(max_length=32, blank=True)
    province = models.CharField(max_length=128, blank=True)
    message_template_key = models.CharField(max_length=64, default="ndvi_drop")
    localized_message = models.TextField(blank=True)
    status = models.CharField(
        max_length=16,
        choices=AlertDeliveryStatus.choices,
        default=AlertDeliveryStatus.PENDING,
        db_index=True,
    )
    raw_reason = models.TextField(blank=True)
    dedupe_key = models.CharField(max_length=256, unique=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("Crop stress event")
        verbose_name_plural = _("Crop stress events")


class WhatsAppDeliveryLog(BaseModel):
    """Outbound WhatsApp attempt for a stress event (Meta Cloud API)."""

    stress_event = models.ForeignKey(
        CropStressEvent,
        on_delete=models.CASCADE,
        related_name="whatsapp_deliveries",
    )
    to_phone_e164 = models.CharField(max_length=32)
    attempt_number = models.PositiveSmallIntegerField(default=1)
    status = models.CharField(max_length=16, choices=AlertDeliveryStatus.choices)
    provider_message_id = models.CharField(max_length=128, blank=True)
    error_code = models.CharField(max_length=64, blank=True)
    error_body = models.TextField(blank=True)
    raw_request = models.JSONField(null=True, blank=True)
    raw_response = models.JSONField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("WhatsApp delivery log")
        verbose_name_plural = _("WhatsApp delivery logs")


class PlantingVerificationRecord(BaseModel):
    """Buyer/contractor planting verification snapshot."""

    polygon = models.ForeignKey(
        TobaccoFieldPolygon,
        on_delete=models.CASCADE,
        related_name="planting_verifications",
    )
    assessed_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(
        max_length=32,
        choices=PlantingVerificationStatus.choices,
        db_index=True,
    )
    confidence = models.FloatField(null=True, blank=True, help_text=_("0–1 optional confidence."))
    notes = models.TextField(blank=True)
    assessed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="planting_verifications_done",
    )

    class Meta:
        ordering = ["-assessed_at"]
        verbose_name = _("Planting verification record")
        verbose_name_plural = _("Planting verification records")
