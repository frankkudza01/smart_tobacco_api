"""
GeoJSON helpers: AgroMonitoring expects a GeoJSON Feature with Polygon geometry.
"""

from __future__ import annotations

import math
from typing import Any


def first_polygon_ring_from_geojson(geo: dict[str, Any]) -> list[list[float]]:
    """Return exterior ring [lon, lat], closed, for area / Agro payload."""
    t = geo.get("type")
    coords = geo.get("coordinates")
    if t == "Polygon" and coords:
        return list(coords[0])
    if t == "MultiPolygon" and coords and coords[0]:
        return list(coords[0][0])
    raise ValueError("Unsupported geometry")


def geojson_to_agromonitoring_feature(name: str, geo: dict[str, Any]) -> dict[str, Any]:
    """Build `{name, geo_json}` body for POST /polygons."""
    ring = first_polygon_ring_from_geojson(geo)
    return {
        "name": name,
        "geo_json": {
            "type": "Feature",
            "properties": {},
            "geometry": {"type": "Polygon", "coordinates": [ring]},
        },
    }


def approximate_area_hectares(geo: dict[str, Any]) -> float:
    """
    Rough planar equivalent area at mean latitude (adequate for hectare checks).
    Not a legal survey — AgroMonitoring returns authoritative area on registration.
    """
    ring = first_polygon_ring_from_geojson(geo)
    if len(ring) < 4:
        return 0.0
    # Drop duplicate closing vertex for shoelace
    pts = ring[:-1] if ring[0] == ring[-1] else ring
    lat0 = math.radians(sum(p[1] for p in pts) / len(pts))
    m_per_deg_lat = 110_574.0
    m_per_deg_lon = 111_320.0 * max(math.cos(lat0), 0.01)
    xs = [p[0] * m_per_deg_lon for p in pts]
    ys = [p[1] * m_per_deg_lat for p in pts]
    n = len(xs)
    a = 0.0
    for i in range(n):
        j = (i + 1) % n
        a += xs[i] * ys[j] - xs[j] * ys[i]
    return abs(a) / 2.0 / 10_000.0
