from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.farms.models import Farm
from apps.tobacco_monitoring.models import GrowthStage, MonitoringStatus, TobaccoFieldPolygon
from apps.tobacco_monitoring.services.geometry import approximate_area_hectares


class Command(BaseCommand):
    help = "Backfill tobacco monitoring polygons from existing farm geofences."

    def handle(self, *args, **options):
        created = 0
        skipped = 0
        qs = Farm.objects.filter(is_active=True).exclude(geofence_geojson__isnull=True)
        for farm in qs.iterator(chunk_size=100):
            if TobaccoFieldPolygon.objects.filter(farm=farm).exists():
                skipped += 1
                continue
            geo = farm.geofence_geojson
            if not isinstance(geo, dict):
                skipped += 1
                continue
            try:
                area = round(approximate_area_hectares(geo), 4)
            except Exception:
                area = 0.0
            polygon = TobaccoFieldPolygon.objects.create(
                farm=farm,
                created_by=farm.owner,
                field_name=f"{(farm.name or 'Farm').strip()} - Auto Boundary",
                crop_type=getattr(settings, "TOBACCO_DEFAULT_CROP", "tobacco"),
                growth_stage=GrowthStage.PRE_PLANT,
                area_hectares=Decimal(str(area)) if area > 0 else None,
                province=(farm.province or "").strip() or "Unknown",
                district=(farm.district or "").strip(),
                ward="",
                monitoring_status=MonitoringStatus.PENDING,
                whatsapp_phone_e164=(getattr(farm.owner, "phone_number", "") or "").strip(),
                geometry_geojson=geo,
                default_alert_language=(getattr(settings, "DEFAULT_ALERT_LANGUAGE", "en") or "en").strip().lower(),
            )
            created += 1

            def _enqueue(pid=str(polygon.id)):
                from apps.tobacco_monitoring.services.agromonitoring import agromonitoring_api_configured
                from apps.tobacco_monitoring.services.polygon_registration import register_polygon_with_provider
                from apps.tobacco_monitoring.tasks import register_polygon_with_agromonitoring_task

                if agromonitoring_api_configured():
                    register_polygon_with_agromonitoring_task.delay(pid)
                else:
                    p = TobaccoFieldPolygon.objects.filter(id=pid).first()
                    if p:
                        register_polygon_with_provider(p)

            transaction.on_commit(_enqueue)
        self.stdout.write(
            self.style.SUCCESS(
                f"Backfill complete. created={created}, skipped={skipped}"
            )
        )
