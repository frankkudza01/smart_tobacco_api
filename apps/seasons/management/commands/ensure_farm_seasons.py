"""
Backfill FarmSeasonAssociation so farms match registration behaviour.

Safe to run repeatedly: uses get_or_create. Default mode only ensures the
current Zimbabwe marketing crop year (same as ensure_default_zimbabwe_season_for_farm).
"""
from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.farms.models import Farm
from apps.seasons.models import FarmSeasonAssociation, Season
from apps.seasons.services import ensure_default_zimbabwe_season_for_farm


class Command(BaseCommand):
    help = (
        "Ensure farms are linked to season(s). "
        "By default: current marketing season only (per Zimbabwe cycle). "
        "Use --link-all-seasons to attach every existing Season row."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--farm-id",
            dest="farm_id",
            default=None,
            help="Only process this farm UUID (primary key).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print actions without writing to the database.",
        )
        parser.add_argument(
            "--link-all-seasons",
            action="store_true",
            help=(
                "For each farm, ensure an association exists for every Season "
                "(historical crop years). Does not create new Season rows."
            ),
        )

    def handle(self, *args, **options):
        farm_id = options["farm_id"]
        dry_run = options["dry_run"]
        link_all = options["link_all_seasons"]

        qs = Farm.objects.all().order_by("created_at")
        if farm_id:
            qs = qs.filter(pk=farm_id)
            if not qs.exists():
                self.stderr.write(self.style.ERROR(f"No farm with id={farm_id!r}"))
                return

        total_farms = qs.count()
        assoc_created = 0

        current_season = None
        if not link_all:
            current_season = _resolve_current_season_for_dry_run()
            if dry_run and current_season is None:
                self.stdout.write(
                    self.style.WARNING(
                        "No Season row for current crop year yet. A real run creates it via "
                        "ensure_default_zimbabwe_season_for_farm."
                    )
                )

        for farm in qs.iterator():
            if link_all:
                for season in Season.objects.order_by("crop_year"):
                    exists = FarmSeasonAssociation.objects.filter(
                        farm=farm, season=season
                    ).exists()
                    if dry_run:
                        if not exists:
                            self.stdout.write(
                                f"[dry-run] Would link farm {farm.pk} ({farm.name!r}) "
                                f"-> season {season.crop_year}"
                            )
                            assoc_created += 1
                    else:
                        _, created = FarmSeasonAssociation.objects.get_or_create(
                            farm=farm,
                            season=season,
                        )
                        if created:
                            assoc_created += 1
                            self.stdout.write(
                                f"Linked farm {farm.pk} ({farm.name!r}) "
                                f"-> season crop_year={season.crop_year}"
                            )
            else:
                if dry_run:
                    linked = (
                        FarmSeasonAssociation.objects.filter(
                            farm=farm, season=current_season
                        ).exists()
                        if current_season
                        else False
                    )
                    if not linked:
                        self.stdout.write(
                            f"[dry-run] Would ensure current season for farm "
                            f"{farm.pk} ({farm.name!r})"
                        )
                        assoc_created += 1
                else:
                    before = FarmSeasonAssociation.objects.filter(farm=farm).count()
                    ensure_default_zimbabwe_season_for_farm(farm)
                    after = FarmSeasonAssociation.objects.filter(farm=farm).count()
                    if after > before:
                        assoc_created += after - before
                        self.stdout.write(
                            f"Ensured season(s) for farm {farm.pk} ({farm.name!r})"
                        )

        summary = (
            f"Done. Farms processed: {total_farms}. "
            f"New association(s): {assoc_created}."
        )
        if dry_run and assoc_created == 0:
            summary += " (nothing missing in dry-run scope)"
        self.stdout.write(self.style.SUCCESS(summary))


def _resolve_current_season_for_dry_run():
    """Match crop_year logic in ensure_default_zimbabwe_season_for_farm (no DB writes)."""
    from datetime import date

    today = date.today()
    season_start_year = today.year if today.month >= 3 else today.year - 1
    return Season.objects.filter(crop_year=season_start_year).first()
