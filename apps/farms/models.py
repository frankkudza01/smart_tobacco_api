from django.conf import settings
from django.db import models

from apps.common.enums import FarmGisVerificationStatus
from apps.common.models import BaseModel
from apps.organizations.models import Organization


class Farm(BaseModel):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="farms",
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="farms",
    )
    name = models.CharField(max_length=255)
    location_description = models.TextField(blank=True, default="")
    latitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    longitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    size_hectares = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    district = models.CharField(max_length=100, blank=True, default="")
    province = models.CharField(max_length=100, blank=True, default="")
    # GeoJSON polygon/multipolygon for farm boundary geofencing.
    geofence_geojson = models.JSONField(null=True, blank=True)
    geofence_horizontal_accuracy_m = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Device horizontal accuracy (m) when boundary/GPS was captured.",
    )
    boundary_check_tolerance_m = models.PositiveSmallIntegerField(
        default=25,
        help_text="Server margin (m) for point-in-farm checks (GPS drift + digitisation).",
    )
    is_active = models.BooleanField(default=True)
    gis_verification_status = models.CharField(
        max_length=16,
        choices=FarmGisVerificationStatus.choices,
        default=FarmGisVerificationStatus.PENDING,
        db_index=True,
    )
    gis_verified_at = models.DateTimeField(null=True, blank=True)
    gis_verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="gis_verified_farms",
    )
    gis_verification_notes = models.TextField(blank=True, default="")

    class Meta:
        db_table = "farms_farm"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["owner", "is_active"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.owner.full_name})"
