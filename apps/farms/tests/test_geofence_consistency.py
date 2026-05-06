import pytest

from apps.farms.geofence import geolocation_geofence_consistency


def _square_ring(center_lon: float, center_lat: float, half_deg: float):
    return {
        "type": "Polygon",
        "coordinates": [
            [
                [center_lon - half_deg, center_lat - half_deg],
                [center_lon + half_deg, center_lat - half_deg],
                [center_lon + half_deg, center_lat + half_deg],
                [center_lon - half_deg, center_lat + half_deg],
                [center_lon - half_deg, center_lat - half_deg],
            ]
        ],
    }


def test_geolocation_inside_polygon_strict():
    gj = _square_ring(31.0, -18.0, 0.02)
    r = geolocation_geofence_consistency(31.0, -18.0, gj, tolerance_m=10, device_horizontal_accuracy_m=None)
    assert r["consistent"] is True
    assert r.get("inside_strict") is True


def test_geolocation_outside_but_within_buffer():
    gj = _square_ring(31.0, -18.0, 0.01)
    # Slightly east of the ring; distance-to-edge should be within tolerance alone.
    r = geolocation_geofence_consistency(
        31.0102,
        -18.0,
        gj,
        tolerance_m=35,
        device_horizontal_accuracy_m=None,
    )
    assert r["consistent"] is True
    assert r.get("mode") == "boundary_buffer"


def test_geolocation_far_outside():
    gj = _square_ring(31.0, -18.0, 0.001)
    r = geolocation_geofence_consistency(
        31.5,
        -18.0,
        gj,
        tolerance_m=5,
        device_horizontal_accuracy_m=5,
    )
    assert r["consistent"] is False
