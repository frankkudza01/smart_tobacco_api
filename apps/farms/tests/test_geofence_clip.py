import pytest

from apps.farms.geofence import (
    _clip_polygon_to_rect,
    administrative_clip_bounds,
    validate_and_normalize_geofence,
)


def test_clip_polygon_rect_keeps_inside_square():
    poly = [(30.0, -18.0), (31.0, -18.0), (31.0, -19.0), (30.0, -19.0), (30.0, -18.0)]
    out = _clip_polygon_to_rect(poly, 30.2, -18.8, 30.8, -18.2)
    assert len(out) >= 4
    for x, y in out[:-1]:
        assert 30.2 <= x <= 30.8
        assert -18.8 <= y <= -18.2


def test_administrative_bounds_mutare():
    b = administrative_clip_bounds("manicaland", "mutare")
    assert b is not None
    min_lon, min_lat, max_lon, max_lat = b
    assert min_lon < max_lon and min_lat < max_lat


def test_validate_and_normalize_requires_minimum_area():
    tiny = {
        "type": "Polygon",
        "coordinates": [
            [
                [30.0, -18.0],
                [30.00001, -18.0],
                [30.00001, -18.00001],
                [30.0, -18.00001],
                [30.0, -18.0],
            ]
        ],
    }
    with pytest.raises(ValueError):
        validate_and_normalize_geofence(
            tiny,
            province="manicaland",
            district="mutare",
            clip_to_admin_region=False,
        )
