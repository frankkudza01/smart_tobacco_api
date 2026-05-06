"""Register polygons with AgroMonitoring and update DB state."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.utils import timezone

from apps.tobacco_monitoring.models import MonitoringStatus
from apps.tobacco_monitoring.services.agromonitoring import (
    AgroMonitoringClient,
    AgroMonitoringError,
)
from apps.tobacco_monitoring.services.geometry import geojson_to_agromonitoring_feature

if TYPE_CHECKING:
    from apps.tobacco_monitoring.models import TobaccoFieldPolygon

logger = logging.getLogger(__name__)


def _client_api_key_ready(client: AgroMonitoringClient) -> bool:
    return bool((getattr(client, "api_key", None) or "").strip())


def register_polygon_with_provider(polygon: TobaccoFieldPolygon, *, client: AgroMonitoringClient | None = None) -> None:
    """
    POST polygon to AgroMonitoring, persist poly id and area.

    Idempotent if `agromonitoring_poly_id` already set (no-op).
    """
    if polygon.agromonitoring_poly_id:
        logger.info("polygon %s already registered as %s", polygon.id, polygon.agromonitoring_poly_id)
        polygon.monitoring_status = MonitoringStatus.ACTIVE
        polygon.save(update_fields=["monitoring_status", "updated_at"])
        return

    client = client or AgroMonitoringClient()
    if not _client_api_key_ready(client):
        logger.warning(
            "Skipping AgroMonitoring registration for polygon %s: AGROMONITORING_API_KEY is not set.",
            polygon.id,
        )
        polygon.monitoring_status = MonitoringStatus.PENDING
        polygon.raw_registration_payload = {
            "detail": "AGROMONITORING_API_KEY is not set. Set it in the environment to register with AgroMonitoring.",
            "skipped": True,
        }
        polygon.save(update_fields=["monitoring_status", "raw_registration_payload", "updated_at"])
        return
    body = geojson_to_agromonitoring_feature(polygon.field_name, polygon.geometry_geojson)
    try:
        resp = client.create_polygon(body, allow_duplicate=False)
    except AgroMonitoringError as exc:
        msg = str(exc)
        if "AGROMONITORING_API_KEY" in msg and (
            "not configured" in msg or "not set" in msg.lower()
        ):
            logger.warning(
                "Skipping AgroMonitoring registration for polygon %s: %s",
                polygon.id,
                exc,
            )
            polygon.monitoring_status = MonitoringStatus.PENDING
            polygon.raw_registration_payload = {"detail": msg, "skipped": True}
            polygon.save(update_fields=["monitoring_status", "raw_registration_payload", "updated_at"])
            return
        logger.exception("AgroMonitoring registration failed for polygon %s: %s", polygon.id, exc)
        polygon.monitoring_status = MonitoringStatus.ERROR
        polygon.save(update_fields=["monitoring_status", "updated_at"])
        raise

    poly_id = (
        resp.get("id")
        or resp.get("_id")
        or resp.get("polyid")
        or resp.get("polygon_id")
    )
    if poly_id is not None:
        poly_id = str(poly_id).strip()
    else:
        poly_id = None
    area = resp.get("area")
    from decimal import Decimal

    polygon.agromonitoring_poly_id = poly_id if poly_id else ""
    polygon.raw_registration_payload = resp
    if area is not None and polygon.area_hectares is None:
        polygon.area_hectares = Decimal(str(area))
    polygon.monitoring_status = MonitoringStatus.ACTIVE if poly_id else MonitoringStatus.ERROR
    polygon.last_imagery_check_at = timezone.now()
    polygon.save(
        update_fields=[
            "agromonitoring_poly_id",
            "raw_registration_payload",
            "area_hectares",
            "monitoring_status",
            "last_imagery_check_at",
            "updated_at",
        ]
    )
