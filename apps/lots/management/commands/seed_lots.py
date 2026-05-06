from __future__ import annotations

from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.common.enums import LotStatus
from apps.lots.models import Lot
from apps.seasons.models import FarmSeasonAssociation


class Command(BaseCommand):
    help = "Seed demo lots directly into DB."

    def add_arguments(self, parser):
        parser.add_argument(
            "--count",
            type=int,
            default=3,
            help="How many lots to create (default: 3).",
        )
        parser.add_argument(
            "--crop-year",
            type=int,
            default=None,
            help="Optional crop year filter (e.g. 2026).",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        count = options["count"]
        crop_year = options["crop_year"]
        if count <= 0:
            raise CommandError("--count must be > 0")

        associations = FarmSeasonAssociation.objects.select_related(
            "farm", "season", "farm__owner"
        )
        if crop_year is not None:
            associations = associations.filter(season__crop_year=crop_year)
        else:
            associations = associations.order_by("-season__crop_year", "farm__created_at")

        associations = list(associations)
        if not associations:
            raise CommandError(
                "No farm-season associations found. Create farm/season first, then rerun."
            )

        year = crop_year or date.today().year
        prefix = f"ZW-{year}-"
        existing = Lot.objects.filter(lot_number__startswith=prefix).values_list(
            "lot_number", flat=True
        )
        seq = 0
        for code in existing:
            try:
                seq = max(seq, int(code.split("-")[-1]))
            except Exception:
                continue

        created = 0
        assoc_index = 0
        while created < count:
            assoc = associations[assoc_index % len(associations)]
            assoc_index += 1
            seq += 1
            lot_number = f"{prefix}{seq:04d}"

            Lot.objects.create(
                farm=assoc.farm,
                season=assoc.season,
                created_by=assoc.farm.owner,
                lot_number=lot_number,
                description="Seeded lot",
                bale_count=1,
                tobacco_type="Virginia Flue-Cured",
                status=LotStatus.REGISTERED,
            )
            created += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {created} lot(s). Latest prefix: {prefix}"
            )
        )
