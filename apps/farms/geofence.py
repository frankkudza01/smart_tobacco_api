"""
Farm geofence helpers: Zimbabwe bounds, administrative region boxes, and
polygon clipping (Sutherland–Hodgman vs axis-aligned rectangle in lon/lat).

Coordinates are always (longitude, latitude) in WGS84 for GeoJSON compatibility.
"""

from __future__ import annotations

import math
from typing import Any

from apps.weather.zimbabwe_regions import (
    match_region_from_district,
    match_region_from_province,
)

# Approximate Zimbabwe land bounding box (min_lat, max_lat, min_lon, max_lon).
ZIMBABWE_BBOX = (-22.52, -15.60, 25.00, 33.05)

_MAX_RING_VERTICES = 256
_MIN_AREA_HA = 0.0005  # ~5 m² — reject degenerate after clip

_EARTH_MEAN_RADIUS_M = 6_371_000.0


def haversine_distance_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Great-circle distance in metres (WGS84 sphere approximation)."""
    rlat1, rlat2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1.0 - a)))
    return _EARTH_MEAN_RADIUS_M * c


def _point_in_polygon_ray_cast(lon: float, lat: float, ring_lon_lat: list[tuple[float, float]]) -> bool:
    """Ray casting; ring may be open or closed."""
    pts = ring_lon_lat[:-1] if len(ring_lon_lat) >= 2 and ring_lon_lat[0] == ring_lon_lat[-1] else ring_lon_lat
    if len(pts) < 3:
        return False
    inside = False
    j = len(pts) - 1
    for i in range(len(pts)):
        xi, yi = pts[i][0], pts[i][1]
        xj, yj = pts[j][0], pts[j][1]
        intersect = (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / (yj - yi + 1e-21) + xi
        if intersect:
            inside = not inside
        j = i
    return inside


def _distance_point_to_segment_m(
    lon: float,
    lat: float,
    a: tuple[float, float],
    b: tuple[float, float],
) -> float:
    """Minimum great-circle distance from point to segment ab, in metres (sampling-based)."""
    lon_a, lat_a = a[0], a[1]
    lon_b, lat_b = b[0], b[1]
    # Project segment to Cartesian at mean latitude for closest-point t
    rad = math.radians((lat_a + lat_b + lat) / 3.0)
    mx = 111_320.0 * max(0.2, abs(math.cos(rad)))
    my = 111_320.0
    ax, ay = math.radians(lon_a) * mx, math.radians(lat_a) * my
    bx, by = math.radians(lon_b) * mx, math.radians(lat_b) * my
    px, py = math.radians(lon) * mx, math.radians(lat) * my
    abx, aby = bx - ax, by - ay
    t = ((px - ax) * abx + (py - ay) * aby) / (abx * abx + aby * aby + 1e-12)
    t = max(0.0, min(1.0, t))
    cx, cy = ax + t * abx, ay + t * aby
    # (cx/mx, cy/my) are radians in projected plane → degrees for haversine
    clon_deg = math.degrees(cx / mx)
    clat_deg = math.degrees(cy / my)
    return haversine_distance_m(clon_deg, clat_deg, lon, lat)


def min_distance_point_to_polygon_ring_m(lon: float, lat: float, ring_lon_lat: list[tuple[float, float]]) -> float:
    pts = list(ring_lon_lat)
    if len(pts) >= 2 and pts[0] == pts[-1]:
        pts = pts[:-1]
    if len(pts) < 2:
        return float("inf")
    best = float("inf")
    n = len(pts)
    for i in range(n):
        d = _distance_point_to_segment_m(lon, lat, pts[i], pts[(i + 1) % n])
        if d < best:
            best = d
    return best


def geolocation_geofence_consistency(
    lon: float,
    lat: float,
    geojson: dict[str, Any],
    *,
    tolerance_m: int,
    device_horizontal_accuracy_m: int | None = None,
) -> dict[str, Any]:
    """
    Decide whether a GPS fix is consistent with a stored farm polygon.

    ``tolerance_m`` is the farm's configured server margin. Device accuracy (if known)
    is added so poor GNSS fixes are not unfairly rejected at the boundary.
    """
    if not isinstance(geojson, dict) or geojson.get("type") != "Polygon":
        return {
            "consistent": False,
            "reason": "no_polygon",
            "inside_strict": False,
            "distance_to_boundary_m": None,
            "effective_tolerance_m": float(tolerance_m),
        }
    coords = geojson.get("coordinates")
    if not isinstance(coords, list) or not coords:
        return {
            "consistent": False,
            "reason": "invalid_coordinates",
            "inside_strict": False,
            "distance_to_boundary_m": None,
            "effective_tolerance_m": float(tolerance_m),
        }
    ring = coords[0]
    if not isinstance(ring, list) or len(ring) < 4:
        return {
            "consistent": False,
            "reason": "ring_too_small",
            "inside_strict": False,
            "distance_to_boundary_m": None,
            "effective_tolerance_m": float(tolerance_m),
        }
    pts: list[tuple[float, float]] = []
    for p in ring:
        if isinstance(p, (list, tuple)) and len(p) >= 2:
            pts.append((float(p[0]), float(p[1])))
    if len(pts) < 4:
        return {
            "consistent": False,
            "reason": "ring_parse_failed",
            "inside_strict": False,
            "distance_to_boundary_m": None,
            "effective_tolerance_m": float(tolerance_m),
        }

    acc = int(device_horizontal_accuracy_m) if device_horizontal_accuracy_m is not None else 0
    eff = float(max(0, int(tolerance_m)) + max(0, acc))

    inside = _point_in_polygon_ray_cast(lon, lat, pts)
    dist_edge = min_distance_point_to_polygon_ring_m(lon, lat, pts)
    if inside:
        return {
            "consistent": True,
            "mode": "inside_polygon",
            "inside_strict": True,
            "distance_to_boundary_m": round(dist_edge, 2),
            "effective_tolerance_m": round(eff, 2),
        }
    if dist_edge <= eff:
        return {
            "consistent": True,
            "mode": "boundary_buffer",
            "inside_strict": False,
            "distance_to_boundary_m": round(dist_edge, 2),
            "effective_tolerance_m": round(eff, 2),
        }
    return {
        "consistent": False,
        "mode": "outside",
        "inside_strict": False,
        "distance_to_boundary_m": round(dist_edge, 2),
        "effective_tolerance_m": round(eff, 2),
    }


def _intersect_segment_x(p1, p2, x_const):
    """Intersection of segment p1-p2 with vertical line x = x_const."""
    x1, y1 = p1
    x2, y2 = p2
    if x1 == x2:
        return (x_const, y1)
    t = (x_const - x1) / (x2 - x1)
    return (x_const, y1 + t * (y2 - y1))


def _intersect_segment_y(p1, p2, y_const):
    """Intersection of segment p1-p2 with horizontal line y = y_const."""
    x1, y1 = p1
    x2, y2 = p2
    if y1 == y2:
        return (x1, y_const)
    t = (y_const - y1) / (y2 - y1)
    return (x1 + t * (x2 - x1), y_const)


def _clip_polygon_to_rect(
    polygon: list[tuple[float, float]],
    min_x: float,
    min_y: float,
    max_x: float,
    max_y: float,
) -> list[tuple[float, float]]:
    """Sutherland–Hodgman clip: polygon (lon, lat) vs axis-aligned rectangle."""
    if len(polygon) < 3:
        return []

    def clip_left(inp):
        out = []
        if not inp:
            return out
        prev = inp[-1]
        for cur in inp:
            pin, cin = prev[0] >= min_x, cur[0] >= min_x
            if cin:
                if not pin:
                    out.append(_intersect_segment_x(prev, cur, min_x))
                out.append(cur)
            elif pin:
                out.append(_intersect_segment_x(prev, cur, min_x))
            prev = cur
        return out

    def clip_right(inp):
        out = []
        if not inp:
            return out
        prev = inp[-1]
        for cur in inp:
            pin, cin = prev[0] <= max_x, cur[0] <= max_x
            if cin:
                if not pin:
                    out.append(_intersect_segment_x(prev, cur, max_x))
                out.append(cur)
            elif pin:
                out.append(_intersect_segment_x(prev, cur, max_x))
            prev = cur
        return out

    def clip_bottom(inp):
        out = []
        if not inp:
            return out
        prev = inp[-1]
        for cur in inp:
            pin, cin = prev[1] >= min_y, cur[1] >= min_y
            if cin:
                if not pin:
                    out.append(_intersect_segment_y(prev, cur, min_y))
                out.append(cur)
            elif pin:
                out.append(_intersect_segment_y(prev, cur, min_y))
            prev = cur
        return out

    def clip_top(inp):
        out = []
        if not inp:
            return out
        prev = inp[-1]
        for cur in inp:
            pin, cin = prev[1] <= max_y, cur[1] <= max_y
            if cin:
                if not pin:
                    out.append(_intersect_segment_y(prev, cur, max_y))
                out.append(cur)
            elif pin:
                out.append(_intersect_segment_y(prev, cur, max_y))
            prev = cur
        return out

    out = list(polygon)
    out = clip_left(out)
    out = clip_right(out)
    out = clip_bottom(out)
    out = clip_top(out)
    if len(out) < 3:
        return []
    # Close ring if needed
    if out[0] != out[-1]:
        out.append(out[0])
    return out


def _polygon_area_ha(ring_lon_lat: list[tuple[float, float]]) -> float:
    """Shoelace area in m² using local equirectangular projection at mean latitude, then ha."""
    if len(ring_lon_lat) < 4:
        return 0.0
    pts = ring_lon_lat[:-1] if ring_lon_lat[0] == ring_lon_lat[-1] else ring_lon_lat
    if len(pts) < 3:
        return 0.0
    mean_lat = sum(p[1] for p in pts) / len(pts)
    rad = math.radians(mean_lat)
    mx = 111_320.0 * math.cos(rad)
    my = 111_320.0
    xs = [math.radians(p[0]) * mx for p in pts]
    ys = [math.radians(p[1]) * my for p in pts]
    n = len(xs)
    s = 0.0
    for i in range(n):
        j = (i + 1) % n
        s += xs[i] * ys[j] - xs[j] * ys[i]
    area_m2 = abs(s) / 2.0
    return area_m2 / 10_000.0


def administrative_clip_bounds(
    province: str | None,
    district: str | None,
) -> tuple[float, float, float, float] | None:
    """
    Return (min_lon, min_lat, max_lon, max_lat) for clipping, derived from the
    same centroid + half-span heuristic as the mobile app.
    """
    province_row = match_region_from_province(province or "")
    district_row = match_region_from_district(district or "")

    def box_from_row(row: dict[str, Any] | None, lat_half: float, lon_half: float):
        if not row:
            return None
        lat = row.get("lat")
        lon = row.get("lon")
        if lat is None or lon is None:
            return None
        lat, lon = float(lat), float(lon)
        return (
            lon - lon_half,
            lat - lat_half,
            lon + lon_half,
            lat + lat_half,
        )

    pb = box_from_row(province_row, 0.65, 0.75)
    db = box_from_row(district_row, 0.22, 0.22)
    if pb and db:
        min_lon = max(pb[0], db[0])
        min_lat = max(pb[1], db[1])
        max_lon = min(pb[2], db[2])
        max_lat = min(pb[3], db[3])
        if min_lon >= max_lon or min_lat >= max_lat:
            return pb
        return (min_lon, min_lat, max_lon, max_lat)
    return db or pb


def clip_geojson_polygon_to_bounds(
    geojson: dict[str, Any],
    bounds: tuple[float, float, float, float],
) -> dict[str, Any]:
    """Return new GeoJSON Polygon outer ring clipped to bounds (min_lon, min_lat, max_lon, max_lat)."""
    min_lon, min_lat, max_lon, max_lat = bounds
    coords = geojson.get("coordinates")
    if not isinstance(coords, list) or not coords:
        return geojson
    ring = coords[0]
    if not isinstance(ring, list):
        return geojson
    pts: list[tuple[float, float]] = []
    for p in ring:
        if not isinstance(p, (list, tuple)) or len(p) < 2:
            continue
        pts.append((float(p[0]), float(p[1])))
    if len(pts) < 3:
        return geojson
    if pts[0] != pts[-1]:
        pts.append(pts[0])
    clipped = _clip_polygon_to_rect(pts, min_lon, min_lat, max_lon, max_lat)
    if len(clipped) < 4:
        return geojson
    ring_out = [[float(x), float(y)] for x, y in clipped]
    return {"type": "Polygon", "coordinates": [ring_out]}


def enforce_zimbabwe_bbox(geojson: dict[str, Any]) -> dict[str, Any]:
    min_lat, max_lat, min_lon, max_lon = ZIMBABWE_BBOX[0], ZIMBABWE_BBOX[1], ZIMBABWE_BBOX[2], ZIMBABWE_BBOX[3]
    return clip_geojson_polygon_to_bounds(geojson, (min_lon, min_lat, max_lon, max_lat))


def validate_and_normalize_geofence(
    geojson: dict[str, Any],
    *,
    province: str | None,
    district: str | None,
    clip_to_admin_region: bool = True,
) -> dict[str, Any]:
    """
    Validate structure, vertex count, Zimbabwe containment, optional admin clip,
    and minimum area.
    """
    if not isinstance(geojson, dict) or geojson.get("type") != "Polygon":
        raise ValueError("geofence must be a GeoJSON Polygon object.")
    coords = geojson.get("coordinates")
    if not isinstance(coords, list) or not coords:
        raise ValueError("Polygon coordinates missing.")
    ring = coords[0]
    if not isinstance(ring, list) or len(ring) < 4:
        raise ValueError("Polygon outer ring must have at least 4 positions (including closure).")
    if len(ring) > _MAX_RING_VERTICES:
        raise ValueError(f"Polygon ring exceeds {_MAX_RING_VERTICES} vertices.")

    # Normalize to closed ring list of [lon, lat]
    norm_ring: list[list[float]] = []
    for p in ring:
        if not isinstance(p, (list, tuple)) or len(p) < 2:
            raise ValueError("Each ring position must be [lon, lat].")
        norm_ring.append([float(p[0]), float(p[1])])
    first = norm_ring[0]
    last = norm_ring[-1]
    if first[0] != last[0] or first[1] != last[1]:
        norm_ring.append([first[0], first[1]])

    gj: dict[str, Any] = {"type": "Polygon", "coordinates": [norm_ring]}

    # Country clip first
    gj = enforce_zimbabwe_bbox(gj)
    if clip_to_admin_region:
        ab = administrative_clip_bounds(province, district)
        if ab is not None:
            gj = clip_geojson_polygon_to_bounds(gj, ab)

    ring_pts = [(p[0], p[1]) for p in gj["coordinates"][0]]
    area = _polygon_area_ha(ring_pts)
    if area < _MIN_AREA_HA:
        raise ValueError("Geofence area is too small after clipping; adjust points or region.")
    return gj
