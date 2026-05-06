"""Verify AGROMONITORING_API_KEY against the live AgroMonitoring API."""

from django.core.management.base import BaseCommand

from apps.tobacco_monitoring.services.agromonitoring import AgroMonitoringClient, AgroMonitoringError


class Command(BaseCommand):
    help = "Call GET /polygons on AgroMonitoring to verify AGROMONITORING_API_KEY and base URL."

    def handle(self, *args, **options):
        try:
            rows = AgroMonitoringClient().list_polygons()
        except AgroMonitoringError as exc:
            self.stderr.write(self.style.ERROR(str(exc)))
            raise SystemExit(1) from exc
        self.stdout.write(
            self.style.SUCCESS(
                f"AgroMonitoring OK — {len(rows)} polygon(s) registered under this API key."
            )
        )
