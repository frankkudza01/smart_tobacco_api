from django.conf import settings
from django.db import models

from apps.common.enums import SeasonStatus
from apps.common.models import BaseModel
from apps.farms.models import Farm


class Season(BaseModel):
    """One canonical season per marketing / crop year for the whole platform.

    All farmers share the same Season row for a given ``crop_year``; farms link
    via ``FarmSeasonAssociation`` (acceptance, etc.). Do not create duplicate
    years — use ``get_or_create`` on ``crop_year`` (see ``seasons.services``).
    """

    crop_year = models.PositiveIntegerField(db_index=True, unique=True)
    name = models.CharField(max_length=100, blank=True, default="")
    status = models.CharField(
        max_length=20,
        choices=SeasonStatus.choices,
        default=SeasonStatus.PLANNING,
    )
    planting_date = models.DateField(null=True, blank=True)
    expected_harvest_date = models.DateField(null=True, blank=True)
    actual_harvest_date = models.DateField(null=True, blank=True)
    expected_yield_kg = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    actual_yield_kg = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    notes = models.TextField(blank=True, default="")

    class Meta:
        db_table = "seasons_season"
        ordering = ["-crop_year", "-created_at"]

    def __str__(self):
        return f"{self.name or 'Season'} - {self.crop_year}"


class FarmSeasonAssociation(BaseModel):
    farm = models.ForeignKey(
        Farm,
        on_delete=models.CASCADE,
        related_name="season_associations",
    )
    season = models.ForeignKey(
        Season,
        on_delete=models.CASCADE,
        related_name="farm_associations",
    )
    farmer_accepted = models.BooleanField(default=False)
    farmer_accepted_at = models.DateTimeField(null=True, blank=True)
    accepted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="accepted_farm_season_associations",
    )

    class Meta:
        db_table = "seasons_farm_association"
        ordering = ["-created_at"]
        unique_together = [["farm", "season"]]

    def __str__(self):
        return f"{self.farm.name} -> {self.season.crop_year}"
