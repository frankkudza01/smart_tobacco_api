from __future__ import annotations

import logging
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.farms.models import Farm
from apps.tobacco_monitoring.models import GrowthStage, MonitoringStatus, TobaccoFieldPolygon
from apps.tobacco_monitoring.services.geometry import approximate_area_hectares

logger = logging.getLogger(__name__)


def _default_polygon_name(farm: Farm) -> str:
    base = (farm.name or "Farm").strip()
    return f"{base} - Auto Boundary"


@receiver(post_save, sender=Farm)
def ensure_tobacco_polygon_from_geofence(sender, instance: Farm, created: bool, **kwargs):
    """
    Automatically create a monitoring polygon from farm geofence when missing.

    This closes the "manual polygon create" gap for farms with valid geofence.
    """
    if not bool(getattr(settings, "TOBACCO_AUTO_CREATE_POLYGON_FROM_GEOFENCE", True)):
        return
    geo = instance.geofence_geojson
    if not isinstance(geo, dict):
        return
    if not instance.is_active:
        return
    if TobaccoFieldPolygon.objects.filter(farm=instance).exists():
        return
    try:
        area = round(approximate_area_hectares(geo), 4)
    except Exception:
        area = 0.0
    polygon = TobaccoFieldPolygon.objects.create(
        farm=instance,
        created_by=instance.owner,
        field_name=_default_polygon_name(instance),
        crop_type=getattr(settings, "TOBACCO_DEFAULT_CROP", "tobacco"),
        growth_stage=GrowthStage.PRE_PLANT,
        area_hectares=Decimal(str(area)) if area > 0 else None,
        province=(instance.province or "").strip() or "Unknown",
        district=(instance.district or "").strip(),
        ward="",
        monitoring_status=MonitoringStatus.PENDING,
        whatsapp_phone_e164=(getattr(instance.owner, "phone_number", "") or "").strip(),
        geometry_geojson=geo,
        default_alert_language=(getattr(settings, "DEFAULT_ALERT_LANGUAGE", "en") or "en").strip().lower(),
    )

    def _enqueue():
        from apps.tobacco_monitoring.services.agromonitoring import agromonitoring_api_configured
        from apps.tobacco_monitoring.services.polygon_registration import register_polygon_with_provider
        from apps.tobacco_monitoring.tasks import register_polygon_with_agromonitoring_task

        if agromonitoring_api_configured():
            register_polygon_with_agromonitoring_task.delay(str(polygon.id))
        else:
            register_polygon_with_provider(polygon)

    transaction.on_commit(_enqueue)
    logger.info(
        "Auto-created tobacco polygon %s from farm %s geofence",
        polygon.id,
        instance.id,
    )
