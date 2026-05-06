"""Validators for tobacco monitoring (provinces, GeoJSON)."""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _


def validate_supported_province(value: str) -> None:
    raw = getattr(settings, "TOBACCO_SUPPORTED_PROVINCES", None) or []
    allowed_lower = {p.strip().lower() for p in raw if p and str(p).strip()}
    if not allowed_lower:
        return
    if value.strip().lower() not in allowed_lower:
        raise ValidationError(
            _("Province must be one of: %(provinces)s"),
            params={"provinces": ", ".join(sorted(raw))},
        )


def validate_geojson_polygon_payload(data: Any) -> dict:
    if not isinstance(data, dict):
        raise ValidationError(_("geometry_geojson must be an object."))
    t = data.get("type")
    if t == "Polygon":
        coords = data.get("coordinates")
        if not coords or not isinstance(coords, list):
            raise ValidationError(_("Invalid Polygon coordinates."))
        ring = coords[0]
        if len(ring) < 4:
            raise ValidationError(_("Polygon ring must have at least 4 positions."))
        first, last = ring[0], ring[-1]
        if first != last:
            raise ValidationError(_("Polygon ring must be closed (first equals last point)."))
        return data
    if t == "MultiPolygon":
        polys = data.get("coordinates")
        if not polys or not isinstance(polys, list):
            raise ValidationError(_("Invalid MultiPolygon coordinates."))
        for poly in polys:
            if not poly or not isinstance(poly, list):
                raise ValidationError(_("Invalid MultiPolygon ring."))
            ring = poly[0]
            if len(ring) < 4 or ring[0] != ring[-1]:
                raise ValidationError(_("Each polygon ring must be closed with at least 4 points."))
        return data
    raise ValidationError(_("Geometry type must be Polygon or MultiPolygon."))
