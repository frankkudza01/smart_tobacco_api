"""Heuristic planting / establishment verification from early NDVI."""

from __future__ import annotations

import logging
from datetime import timedelta

from django.conf import settings
from django.db.models import Avg
from django.utils import timezone

from apps.tobacco_monitoring.models import (
    GrowthStage,
    MetricType,
    PlantingVerificationRecord,
    PlantingVerificationStatus,
    TobaccoFieldPolygon,
)

logger = logging.getLogger(__name__)


def auto_assess_planting_if_applicable(polygon: TobaccoFieldPolygon) -> PlantingVerificationRecord | None:
    """
    After new NDVI observations, refresh an automated verification row (idempotent per day).
    Uses mean NDVI in transplant / early vegetative window as emergence proxy.
    """
    if polygon.growth_stage not in (GrowthStage.TRANSPLANT, GrowthStage.VEGETATIVE, GrowthStage.PRE_PLANT):
        return None

    today = timezone.now().date()
    threshold = float(getattr(settings, "TOBACCO_PLANTING_NDVI_THRESHOLD", 0.25))

    avg_ndvi = (
        polygon.observations.filter(metric_type=MetricType.NDVI)
        .filter(observation_date__gte=today - timedelta(days=45))
        .aggregate(a=Avg("metric_value"))
        .get("a")
    )
    if avg_ndvi is None:
        return None

    mean_v = float(avg_ndvi)
    if mean_v >= threshold + 0.1:
        status = PlantingVerificationStatus.ESTABLISHED
        confidence = min(0.95, 0.5 + mean_v)
    elif mean_v >= threshold:
        status = PlantingVerificationStatus.PARTIALLY_ESTABLISHED
        confidence = 0.55
    else:
        status = PlantingVerificationStatus.NOT_DETECTED
        confidence = max(0.2, 1.0 - mean_v * 2)

    notes = f"Auto assessment from mean NDVI {mean_v:.3f} (threshold {threshold})."

    existing = polygon.planting_verifications.filter(assessed_at__date=today).first()
    if existing:
        existing.status = status
        existing.confidence = confidence
        existing.notes = notes
        existing.save(update_fields=["status", "confidence", "notes", "updated_at"])
        return existing

    rec = PlantingVerificationRecord.objects.create(
        polygon=polygon,
        status=status,
        confidence=confidence,
        notes=notes,
        assessed_by=None,
    )
    logger.info("Planting verification %s for polygon %s status=%s", rec.id, polygon.id, status)
    return rec
