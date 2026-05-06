"""Sequential lot numbers scoped to farm + season (ties each lot to a crop year)."""

from __future__ import annotations

from django.db import transaction

from apps.farms.models import Farm
from apps.lots.models import Lot
from apps.seasons.models import Season


def generate_lot_number_for_farm_season(farm: Farm, season: Season) -> str:
    """
    Allocate the next lot number for this farm and season.

    Pattern: ``{crop_year}-F{farm_8hex}-{seq:04d}``

    - ``crop_year`` comes from the season (marketing year).
    - ``farm_8hex`` is the first 8 hex digits of the farm UUID (stable, readable tie to farm).
    - ``seq`` is a 1-based counter of lots already on this farm+season, incremented until
      ``lot_number`` is globally free (unique constraint).

    Example: ``2026-F3A9B1C2-0003``
    """
    year = int(season.crop_year)
    farm_key = str(farm.id).replace("-", "")[:8].upper()
    prefix = f"{year}-F{farm_key}"
    with transaction.atomic():
        Farm.objects.select_for_update().only("id").get(pk=farm.pk)
        seq = Lot.objects.filter(farm_id=farm.id, season_id=season.id).count() + 1
        while True:
            candidate = f"{prefix}-{seq:04d}"
            if not Lot.objects.filter(lot_number=candidate).exists():
                return candidate
            seq += 1
