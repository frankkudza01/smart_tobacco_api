"""
Enqueue Celery registration for tobacco polygons missing AgroMonitoring id.

Use after setting AGROMONITORING_API_KEY or fixing geometry errors.
"""

from django.core.management.base import BaseCommand
from django.db.models import Q

from apps.tobacco_monitoring.models import MonitoringStatus, TobaccoFieldPolygon
from apps.tobacco_monitoring.services.agromonitoring import agromonitoring_api_configured
from apps.tobacco_monitoring.tasks import register_polygon_with_agromonitoring_task


class Command(BaseCommand):
    help = (
        "Queue register_polygon_with_agromonitoring_task for polygons with no "
        "agromonitoring_poly_id but valid geometry (e.g. after adding API key)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Only print polygon IDs that would be enqueued.",
        )

    def handle(self, *args, **options):
        dry = options["dry_run"]
        if not agromonitoring_api_configured():
            self.stdout.write(
                self.style.ERROR(
                    "AGROMONITORING_API_KEY is not set. Set it, then run this command again."
                )
            )
            return
        qs = (
            TobaccoFieldPolygon.objects.filter(
                Q(agromonitoring_poly_id__isnull=True) | Q(agromonitoring_poly_id=""),
                is_active=True,
            )
            .exclude(geometry_geojson__isnull=True)
            .exclude(geometry_geojson={})
        )
        polygons = list(qs)
        if not polygons:
            self.stdout.write(self.style.WARNING("No pending polygons found."))
            return
        self.stdout.write(f"Found {len(polygons)} polygon(s) pending AgroMonitoring registration.")
        for p in polygons:
            if p.monitoring_status == MonitoringStatus.ERROR:
                p.monitoring_status = MonitoringStatus.PENDING
                p.save(update_fields=["monitoring_status", "updated_at"])
        for p in polygons:
            pid = p.id
            if dry:
                self.stdout.write(f"  would enqueue {pid}")
            else:
                register_polygon_with_agromonitoring_task.delay(str(pid))
                self.stdout.write(f"  enqueued {pid}")
        if not dry:
            self.stdout.write(self.style.SUCCESS("Done. Ensure Celery worker is running."))
