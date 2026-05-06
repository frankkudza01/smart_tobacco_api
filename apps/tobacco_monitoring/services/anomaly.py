"""Rule-based tobacco crop stress detection (NDVI + soil moisture)."""

from __future__ import annotations

import logging

from django.conf import settings
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from apps.tobacco_monitoring.models import (
    AlertDeliveryStatus,
    CropStressEvent,
    CropStressEventType,
    GrowthStage,
    MetricType,
    PolygonObservation,
    StressSeverity,
    TobaccoFieldPolygon,
)
from apps.tobacco_monitoring.services.alert_messages import render_ndvi_drop_message

logger = logging.getLogger(__name__)


def _severity_for_drop(pct: float) -> str:
    if pct >= 25:
        return StressSeverity.HIGH
    if pct >= 15:
        return StressSeverity.MEDIUM
    return StressSeverity.LOW


def _create_event_and_enqueue(
    *,
    polygon: TobaccoFieldPolygon,
    event_type: str,
    severity: str,
    observation_date,
    dedupe_key: str,
    localized_message: str,
    raw_reason: str,
    previous_value: float | None = None,
    current_value: float | None = None,
    percentage_change: float | None = None,
    message_template_key: str = "ndvi_drop",
) -> CropStressEvent | None:
    if CropStressEvent.objects.filter(dedupe_key=dedupe_key).exists():
        return None
    with transaction.atomic():
        event = CropStressEvent.objects.create(
            polygon=polygon,
            event_type=event_type,
            severity=severity,
            observation_date=observation_date,
            previous_ndvi=previous_value,
            current_ndvi=current_value,
            percentage_change=percentage_change,
            growth_stage=polygon.growth_stage,
            season=polygon.season or "",
            province=polygon.province or "",
            message_template_key=message_template_key,
            localized_message=localized_message,
            status=AlertDeliveryStatus.PENDING,
            raw_reason=raw_reason,
            dedupe_key=dedupe_key,
        )

    def _enqueue():
        from apps.tobacco_monitoring.tasks import send_crop_stress_whatsapp_task

        send_crop_stress_whatsapp_task.delay(str(event.id))

    transaction.on_commit(_enqueue)
    return event


def evaluate_ndvi_drop_for_polygon(polygon: TobaccoFieldPolygon) -> CropStressEvent | None:
    """
    If latest NDVI dropped by >= configured % vs previous valid observation during vegetative stage,
    create a deduplicated CropStressEvent and queue WhatsApp.
    """
    threshold = float(getattr(settings, "NDVI_STRESS_DROP_THRESHOLD", 10.0))
    if polygon.growth_stage != GrowthStage.VEGETATIVE:
        return None

    latest = (
        PolygonObservation.objects.filter(polygon=polygon, metric_type=MetricType.NDVI)
        .order_by("-observation_date")
        .first()
    )
    if not latest:
        return None
    prev = (
        PolygonObservation.objects.filter(
            polygon=polygon,
            metric_type=MetricType.NDVI,
            observation_date__lt=latest.observation_date,
        )
        .order_by("-observation_date")
        .first()
    )
    if not prev or prev.metric_value <= 0:
        return None

    prev_v = float(prev.metric_value)
    cur_v = float(latest.metric_value)
    pct_change = (cur_v - prev_v) / prev_v * 100.0
    if pct_change > -threshold:
        return None

    pct_drop = abs(pct_change)
    msg = render_ndvi_drop_message(polygon, pct_drop=pct_drop, lang=polygon.default_alert_language or "en")
    reason = (
        f"NDVI fell from {prev_v:.4f} to {cur_v:.4f} ({pct_change:.2f}%) "
        f"between {prev.observation_date} and {latest.observation_date} (threshold {threshold}%)."
    )
    event = _create_event_and_enqueue(
        polygon=polygon,
        event_type=CropStressEventType.NDVI_DROP,
        severity=_severity_for_drop(pct_drop),
        observation_date=latest.observation_date,
        dedupe_key=f"{polygon.id}:{latest.observation_date.isoformat()}:ndvi_drop",
        localized_message=msg,
        raw_reason=reason,
        previous_value=prev_v,
        current_value=cur_v,
        percentage_change=round(pct_change, 4),
        message_template_key="ndvi_drop",
    )
    if event:
        logger.info("Created NDVI crop stress event %s for polygon %s", event.id, polygon.id)
    return event


def evaluate_soil_moisture_stress_for_polygon(polygon: TobaccoFieldPolygon) -> CropStressEvent | None:
    """Detect abnormal soil moisture stress from latest two observations."""
    threshold = float(getattr(settings, "SOIL_MOISTURE_STRESS_THRESHOLD", 0.18))
    drop_threshold_pct = float(getattr(settings, "SOIL_MOISTURE_DROP_THRESHOLD_PCT", 20.0))
    latest = (
        PolygonObservation.objects.filter(polygon=polygon, metric_type=MetricType.SOIL_MOISTURE)
        .order_by("-observation_date")
        .first()
    )
    if not latest:
        return None
    prev = (
        PolygonObservation.objects.filter(
            polygon=polygon,
            metric_type=MetricType.SOIL_MOISTURE,
            observation_date__lt=latest.observation_date,
        )
        .order_by("-observation_date")
        .first()
    )
    if not prev:
        return None
    prev_v = float(prev.metric_value)
    cur_v = float(latest.metric_value)
    if prev_v <= 0:
        return None
    drop_pct = max(0.0, ((prev_v - cur_v) / prev_v) * 100.0)
    crossed_absolute = prev_v >= threshold and cur_v < threshold
    if not crossed_absolute and drop_pct < drop_threshold_pct:
        return None
    if cur_v < threshold * 0.6 or drop_pct >= 40:
        severity = StressSeverity.HIGH
    elif cur_v < threshold * 0.8 or drop_pct >= 30:
        severity = StressSeverity.MEDIUM
    else:
        severity = StressSeverity.LOW
    reason = (
        f"Soil moisture dropped from {prev_v:.4f} to {cur_v:.4f} ({drop_pct:.2f}%) "
        f"between {prev.observation_date} and {latest.observation_date}; "
        f"threshold={threshold:.3f}, drop_threshold={drop_threshold_pct:.1f}%."
    )
    from apps.tobacco_monitoring.services.alert_messages import render_moisture_stress_message

    msg = render_moisture_stress_message(
        polygon,
        moisture_value=cur_v,
        drop_pct=drop_pct,
        lang=polygon.default_alert_language or "en",
    )
    event = _create_event_and_enqueue(
        polygon=polygon,
        event_type=CropStressEventType.MOISTURE_STRESS,
        severity=severity,
        observation_date=latest.observation_date,
        dedupe_key=f"{polygon.id}:{latest.observation_date.isoformat()}:moisture_stress",
        localized_message=msg,
        raw_reason=reason,
        previous_value=prev_v,
        current_value=cur_v,
        percentage_change=round(-drop_pct, 4),
        message_template_key="moisture_stress",
    )
    if event:
        logger.info("Created moisture stress event %s for polygon %s", event.id, polygon.id)
    return event


def evaluate_monitoring_rules_for_polygon(polygon: TobaccoFieldPolygon) -> list[CropStressEvent]:
    """Run all stress rules for a polygon and return created events."""
    created: list[CropStressEvent] = []
    ndvi = evaluate_ndvi_drop_for_polygon(polygon)
    if ndvi:
        created.append(ndvi)
    moisture = evaluate_soil_moisture_stress_for_polygon(polygon)
    if moisture:
        created.append(moisture)
    return created


def refresh_polygon_monitoring_timestamps(polygon: TobaccoFieldPolygon, imagery_date) -> None:
    polygon.last_imagery_check_at = timezone.now()
    if imagery_date:
        current_max = polygon.observations.aggregate(m=Max("observation_date"))["m"]
        if current_max:
            polygon.last_successful_imagery_date = current_max
    polygon.save(update_fields=["last_imagery_check_at", "last_successful_imagery_date", "updated_at"])
