from __future__ import annotations

from datetime import date

from apps.common.enums import SeasonStatus
from apps.seasons.models import FarmSeasonAssociation, Season


def ensure_default_zimbabwe_season_for_farm(farm) -> Season:
    """
    Create (or return existing) farm season aligned to Zimbabwe tobacco cycle.

    Marketing season starts in March.
    Seedbed preparation starts June 1.
    Transplanting starts September 1.
    Harvest window spans January to July (we store expected harvest as July 1).
    """
    today = date.today()
    season_start_year = today.year if today.month >= 3 else today.year - 1
    crop_year = season_start_year

    season, _ = Season.objects.get_or_create(
        crop_year=crop_year,
        defaults={
            "name": f"{season_start_year}/{(season_start_year + 1) % 100:02d} Marketing Season",
            "status": _status_for_date(today, season_start_year),
            "planting_date": date(season_start_year, 9, 1),
            "expected_harvest_date": date(season_start_year + 1, 7, 1),
            "notes": (
                "System-generated season (Zimbabwe cycle): "
                "marketing in Mar, seedbed from Jun 1, transplanting from Sep, "
                "harvest Jan-Jul."
            ),
        },
    )
    FarmSeasonAssociation.objects.get_or_create(
        farm=farm,
        season=season,
    )
    return season


def _status_for_date(today: date, season_start_year: int) -> str:
    seedbed_start = date(season_start_year, 6, 1)
    transplant_start = date(season_start_year, 9, 1)
    harvest_start = date(season_start_year + 1, 1, 1)
    harvest_end = date(season_start_year + 1, 7, 31)

    if today < transplant_start:
        return SeasonStatus.PLANNING
    if harvest_start <= today <= harvest_end:
        return SeasonStatus.HARVESTING
    if today > harvest_end:
        return SeasonStatus.COMPLETED
    return SeasonStatus.ACTIVE
