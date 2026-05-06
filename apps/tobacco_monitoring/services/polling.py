"""
Poll AgroMonitoring for NDVI / soil moisture and persist idempotent observations.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

import requests
from django.db import transaction
from django.db.models import Max
from django.utils import timezone as django_timezone

from apps.tobacco_monitoring.models import (
    MetricType,
    MonitoringStatus,
    PolygonObservation,
    SatelliteImageryRecord,
    TobaccoFieldPolygon,
)
from apps.tobacco_monitoring.services.agromonitoring import (
    AgroMonitoringClient,
    AgroMonitoringError,
    looks_like_agromonitoring_polygon_id,
)
from apps.tobacco_monitoring.services.anomaly import evaluate_monitoring_rules_for_polygon
from apps.tobacco_monitoring.services.planting_verification import auto_assess_planting_if_applicable

logger = logging.getLogger(__name__)

CLOUD_MAX = 90.0  # still store marginal scenes; tighten in product if needed


def _utc_date_from_ts(ts: int) -> date:
    return datetime.fromtimestamp(int(ts), tz=timezone.utc).date()


def _ensure_agromonitoring_poly_id(
    polygon: TobaccoFieldPolygon,
    client: AgroMonitoringClient,
    summary: dict[str, Any],
) -> str | None:
    """
    Return a usable AgroMonitoring hex polygon id.

    If the DB value is missing or not a provider id, match ``GET /polygons`` by
    ``field_name`` (same as the name sent on registration) and persist the id.
    """
    cur = (polygon.agromonitoring_poly_id or "").strip()
    if looks_like_agromonitoring_polygon_id(cur):
        return cur
    try:
        resolved = client.resolve_polygon_id_for_field_name(polygon.field_name or "")
    except (requests.ConnectionError, requests.Timeout) as exc:
        summary["errors"].append("agromonitoring_transport_error")
        logger.warning(
            "Could not reach AgroMonitoring to resolve polygon id for %s (DNS/network). %s",
            polygon.id,
            exc,
        )
        return None
    if not resolved or not looks_like_agromonitoring_polygon_id(resolved):
        summary["errors"].append("could_not_resolve_agromonitoring_poly_id")
        logger.warning(
            "No AgroMonitoring polygon id for tobacco polygon %s (stored=%r, field_name=%r). "
            "Register the field or ensure `field_name` matches the polygon name in AgroMonitoring "
            "for this API key.",
            polygon.id,
            cur[:80] if cur else "",
            (polygon.field_name or "")[:120],
        )
        return None
    if resolved != cur:
        summary["resolved_agromonitoring_poly_id"] = resolved
        logger.info(
            "Linked AgroMonitoring polygon id for %s via provider list (was %r -> %s)",
            polygon.id,
            cur[:48] if cur else "",
            resolved,
        )
    TobaccoFieldPolygon.objects.filter(pk=polygon.pk).update(
        agromonitoring_poly_id=resolved,
        updated_at=django_timezone.now(),
    )
    polygon.agromonitoring_poly_id = resolved
    return resolved


def poll_polygon_imagery(
    polygon: TobaccoFieldPolygon,
    *,
    client: AgroMonitoringClient | None = None,
    lookback_days: int = 30,
) -> dict[str, Any]:
    """
    Fetch NDVI + soil history, upsert observations and imagery records.

    Returns a small summary dict for logging/metrics.
    """
    client = client or AgroMonitoringClient()
    summary: dict[str, Any] = {"polygon_id": str(polygon.id), "ndvi_rows": 0, "soil_rows": 0, "errors": []}

    if not (getattr(client, "api_key", None) or "").strip():
        summary["errors"].append("api_key_not_configured")
        summary["skipped"] = True
        return summary

    poly_id = (polygon.agromonitoring_poly_id or "").strip()
    if not poly_id:
        summary["errors"].append("missing_agromonitoring_poly_id")
        poly_id = _ensure_agromonitoring_poly_id(polygon, client, summary) or ""
        if not poly_id:
            return summary
    elif not looks_like_agromonitoring_polygon_id(poly_id):
        poly_id = _ensure_agromonitoring_poly_id(polygon, client, summary) or ""
        if not poly_id:
            return summary

    # Use UTC calendar dates for AgroMonitoring windows. ``now().date()`` in the project
    # timezone can be "tomorrow" vs UTC and produce ``end`` after the API's ``now``.
    end = django_timezone.now().astimezone(timezone.utc).date()
    start = end - timedelta(days=lookback_days)

    try:
        ndvi_rows = client.ndvi_history(poly_id, start, end)
    except (requests.ConnectionError, requests.Timeout) as exc:
        logger.warning(
            "NDVI poll skipped polygon=%s agromonitoring_poly_id=%s: cannot reach AgroMonitoring "
            "(check internet/DNS/firewall or AGROMONITORING_BASE_URL). %s",
            polygon.id,
            poly_id,
            exc,
        )
        summary["errors"].append("agromonitoring_transport_error")
        ndvi_rows = []
    except AgroMonitoringError as exc:
        msg = str(exc)
        if "HTTP 400" in msg or "HTTP 404" in msg:
            try:
                alt = client.resolve_polygon_id_for_field_name(polygon.field_name or "")
            except (requests.ConnectionError, requests.Timeout) as net_exc:
                summary["errors"].append("agromonitoring_transport_error")
                summary["errors"].append(msg)
                logger.warning(
                    "NDVI HTTP 400 for polygon=%s but could not re-list polygons (network). %s",
                    polygon.id,
                    net_exc,
                )
                ndvi_rows = []
            else:
                if (
                    alt
                    and looks_like_agromonitoring_polygon_id(alt)
                    and alt != poly_id
                ):
                    summary["retried_ndvi_after_resolving_poly_id"] = alt
                    TobaccoFieldPolygon.objects.filter(pk=polygon.pk).update(
                        agromonitoring_poly_id=alt,
                        updated_at=django_timezone.now(),
                    )
                    polygon.agromonitoring_poly_id = alt
                    try:
                        ndvi_rows = client.ndvi_history(alt, start, end)
                    except (requests.ConnectionError, requests.Timeout) as exc2:
                        logger.warning(
                            "NDVI poll skipped polygon=%s after re-linking poly id: %s",
                            polygon.id,
                            exc2,
                        )
                        summary["errors"].append("agromonitoring_transport_error")
                        ndvi_rows = []
                    except AgroMonitoringError as exc2:
                        logger.warning(
                            "NDVI poll failed polygon=%s agromonitoring_poly_id=%s err=%s",
                            polygon.id,
                            alt,
                            exc2,
                        )
                        summary["errors"].append(str(exc2))
                        ndvi_rows = []
                else:
                    logger.warning(
                        "NDVI poll failed polygon=%s agromonitoring_poly_id=%s err=%s",
                        polygon.id,
                        poly_id,
                        exc,
                    )
                    summary["errors"].append(msg)
                    ndvi_rows = []
        else:
            logger.warning(
                "NDVI poll failed polygon=%s agromonitoring_poly_id=%s err=%s",
                polygon.id,
                poly_id,
                exc,
            )
            summary["errors"].append(msg)
            ndvi_rows = []

    soil_rows: list[dict[str, Any]] = []
    try:
        soil_rows = client.soil_history(poly_id, start, end)
    except (requests.ConnectionError, requests.Timeout) as exc:
        logger.warning(
            "Soil poll skipped polygon=%s: cannot reach AgroMonitoring. %s",
            polygon.id,
            exc,
        )
        summary["errors"].append("agromonitoring_transport_error_soil")
    except AgroMonitoringError as exc:
        logger.warning("Soil poll failed polygon=%s err=%s", polygon.id, exc)
        summary["errors"].append(f"soil:{exc}")

    summary["ndvi_rows"] = len(ndvi_rows)
    summary["soil_rows"] = len(soil_rows)

    with transaction.atomic():
        for row in ndvi_rows:
            ts = row.get("dt")
            if not ts:
                continue
            obs_date = _utc_date_from_ts(int(ts))
            cl = float(row.get("cl") or 0) * 100 if row.get("cl") is not None else None
            if cl is not None and cl > CLOUD_MAX:
                continue
            data = row.get("data") or {}
            mean = data.get("mean")
            if mean is None:
                continue
            source = str(row.get("source") or "mixed")
            scene_id = f"{source}:{ts}"
            idem = f"{polygon.id}:{obs_date.isoformat()}:{source}:imagery"

            SatelliteImageryRecord.objects.update_or_create(
                idempotency_key=idem,
                defaults={
                    "polygon": polygon,
                    "acquisition_date": obs_date,
                    "source": source,
                    "cloud_cover": cl,
                    "scene_id": scene_id,
                    "raw_payload": row,
                    "processed": True,
                },
            )

            PolygonObservation.objects.update_or_create(
                polygon=polygon,
                observation_date=obs_date,
                metric_type=MetricType.NDVI,
                defaults={
                    "metric_value": float(mean),
                    "source": "agromonitoring",
                    "scene_id": scene_id,
                    "cloud_cover": cl,
                    "raw_payload": row,
                },
            )

        for row in soil_rows:
            ts = row.get("dt")
            moisture = row.get("moisture")
            if not ts or moisture is None:
                continue
            obs_date = _utc_date_from_ts(int(ts))
            PolygonObservation.objects.update_or_create(
                polygon=polygon,
                observation_date=obs_date,
                metric_type=MetricType.SOIL_MOISTURE,
                defaults={
                    "metric_value": float(moisture),
                    "source": "agromonitoring_soil",
                    "scene_id": f"soil:{ts}",
                    "cloud_cover": None,
                    "raw_payload": row,
                },
            )

    polygon.last_imagery_check_at = django_timezone.now()
    max_ndvi_date = polygon.observations.filter(metric_type=MetricType.NDVI).aggregate(m=Max("observation_date"))["m"]
    if max_ndvi_date:
        polygon.last_successful_imagery_date = max_ndvi_date
    polygon.save(update_fields=["last_imagery_check_at", "last_successful_imagery_date", "updated_at"])

    evaluate_monitoring_rules_for_polygon(polygon)
    auto_assess_planting_if_applicable(polygon)

    return summary
