from django.conf import settings
from django.db import models

from apps.common.enums import LotStatus
from apps.common.models import BaseModel
from apps.farms.models import Farm
from apps.seasons.models import Season


class Lot(BaseModel):
    farm = models.ForeignKey(Farm, on_delete=models.CASCADE, related_name="lots")
    season = models.ForeignKey(Season, on_delete=models.CASCADE, related_name="lots")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_lots",
    )
    lot_number = models.CharField(max_length=100, unique=True, db_index=True)
    description = models.TextField(blank=True, default="")
    weight_kg = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    bale_count = models.PositiveIntegerField(default=1)
    tobacco_type = models.CharField(max_length=50, blank=True, default="")
    status = models.CharField(
        max_length=20,
        choices=LotStatus.choices,
        default=LotStatus.DRAFT,
        db_index=True,
    )
    blockchain_anchor_hash = models.CharField(max_length=66, blank=True, default="")

    class Meta:
        db_table = "lots_lot"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "created_at"]),
        ]

    def __str__(self):
        return f"Lot {self.lot_number} ({self.status})"
