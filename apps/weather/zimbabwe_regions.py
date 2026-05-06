"""
Zimbabwe weather reference points: provinces + district / town coordinates (WGS84).

`kind` is ``province`` or ``district``. Districts include ``parent_code`` linking to the
province centroid group for reporting. Used for OpenWeatherMap lat/lon queries.
"""

from __future__ import annotations

from typing import Any

# Province-level (broad coverage).
_PROVINCES: list[dict[str, Any]] = [
    {"code": "harare", "name": "Harare", "lat": -17.8252, "lon": 31.0335, "kind": "province"},
    {"code": "bulawayo", "name": "Bulawayo", "lat": -20.1547, "lon": 28.5847, "kind": "province"},
    {"code": "manicaland", "name": "Manicaland", "lat": -18.9707, "lon": 32.6709, "kind": "province"},
    {
        "code": "mashonaland_central",
        "name": "Mashonaland Central",
        "lat": -17.3667,
        "lon": 31.0500,
        "kind": "province",
    },
    {"code": "mashonaland_east", "name": "Mashonaland East", "lat": -17.8065, "lon": 31.0534, "kind": "province"},
    {"code": "mashonaland_west", "name": "Mashonaland West", "lat": -17.8200, "lon": 29.8800, "kind": "province"},
    {"code": "masvingo", "name": "Masvingo", "lat": -20.0744, "lon": 30.8329, "kind": "province"},
    {"code": "matabeleland_north", "name": "Matabeleland North", "lat": -18.5300, "lon": 27.4800, "kind": "province"},
    {"code": "matabeleland_south", "name": "Matabeleland South", "lat": -21.0500, "lon": 29.0167, "kind": "province"},
    {"code": "midlands", "name": "Midlands", "lat": -19.4500, "lon": 29.8167, "kind": "province"},
]

# District / town — finer points for farm.district matching and `region=` queries.
_DISTRICTS: list[dict[str, Any]] = [
    # Harare surrounds
    {"code": "chitungwiza", "name": "Chitungwiza", "lat": -18.0128, "lon": 31.0756, "kind": "district", "parent_code": "harare"},
    {"code": "epworth", "name": "Epworth", "lat": -17.8900, "lon": 31.1380, "kind": "district", "parent_code": "harare"},
    # Manicaland
    {"code": "mutare", "name": "Mutare", "lat": -18.9707, "lon": 32.6709, "kind": "district", "parent_code": "manicaland"},
    {"code": "rusape", "name": "Rusape", "lat": -18.5278, "lon": 32.1281, "kind": "district", "parent_code": "manicaland"},
    {"code": "chipinge", "name": "Chipinge", "lat": -20.1883, "lon": 32.6261, "kind": "district", "parent_code": "manicaland"},
    {"code": "nyanga", "name": "Nyanga", "lat": -18.2117, "lon": 32.9278, "kind": "district", "parent_code": "manicaland"},
    {"code": "chimanimani", "name": "Chimanimani", "lat": -19.8047, "lon": 32.8719, "kind": "district", "parent_code": "manicaland"},
    # Mashonaland East
    {"code": "marondera", "name": "Marondera", "lat": -18.1853, "lon": 31.5519, "kind": "district", "parent_code": "mashonaland_east"},
    {"code": "murehwa", "name": "Murehwa", "lat": -17.6458, "lon": 31.7889, "kind": "district", "parent_code": "mashonaland_east"},
    {"code": "wedza", "name": "Wedza", "lat": -18.7394, "lon": 31.3278, "kind": "district", "parent_code": "mashonaland_east"},
    # Mashonaland Central
    {"code": "bindura", "name": "Bindura", "lat": -17.3019, "lon": 31.3306, "kind": "district", "parent_code": "mashonaland_central"},
    {"code": "shamva", "name": "Shamva", "lat": -17.3192, "lon": 31.5684, "kind": "district", "parent_code": "mashonaland_central"},
    {"code": "mvurwi", "name": "Mvurwi", "lat": -17.0317, "lon": 30.8597, "kind": "district", "parent_code": "mashonaland_central"},
    # Mashonaland West
    {"code": "chinhoyi", "name": "Chinhoyi", "lat": -17.3667, "lon": 30.2000, "kind": "district", "parent_code": "mashonaland_west"},
    {"code": "kariba", "name": "Kariba", "lat": -16.5167, "lon": 28.8000, "kind": "district", "parent_code": "mashonaland_west"},
    {"code": "kadoma", "name": "Kadoma", "lat": -18.3333, "lon": 29.9167, "kind": "district", "parent_code": "mashonaland_west"},
    {"code": "norton", "name": "Norton", "lat": -17.8833, "lon": 30.7000, "kind": "district", "parent_code": "mashonaland_west"},
    # Midlands
    {"code": "gweru", "name": "Gweru", "lat": -19.4500, "lon": 29.8167, "kind": "district", "parent_code": "midlands"},
    {"code": "kwekwe", "name": "Kwekwe", "lat": -20.0500, "lon": 29.6833, "kind": "district", "parent_code": "midlands"},
    {"code": "shurugwi", "name": "Shurugwi", "lat": -20.5058, "lon": 30.0056, "kind": "district", "parent_code": "midlands"},
    {"code": "zvishavane", "name": "Zvishavane", "lat": -20.3264, "lon": 30.0664, "kind": "district", "parent_code": "midlands"},
    # Masvingo
    {"code": "masvingo_city", "name": "Masvingo (city)", "lat": -20.0744, "lon": 30.8329, "kind": "district", "parent_code": "masvingo"},
    {"code": "chiredzi", "name": "Chiredzi", "lat": -21.0333, "lon": 31.6667, "kind": "district", "parent_code": "masvingo"},
    {"code": "gutu", "name": "Gutu", "lat": -19.6667, "lon": 30.9500, "kind": "district", "parent_code": "masvingo"},
    {"code": "zaka", "name": "Zaka", "lat": -20.3167, "lon": 31.4833, "kind": "district", "parent_code": "masvingo"},
    # Matabeleland North
    {"code": "victoria_falls", "name": "Victoria Falls", "lat": -17.9318, "lon": 25.8307, "kind": "district", "parent_code": "matabeleland_north"},
    {"code": "hwange", "name": "Hwange", "lat": -18.3656, "lon": 26.5019, "kind": "district", "parent_code": "matabeleland_north"},
    {"code": "lupane", "name": "Lupane", "lat": -18.9315, "lon": 27.8078, "kind": "district", "parent_code": "matabeleland_north"},
    # Matabeleland South
    {"code": "gwanda", "name": "Gwanda", "lat": -20.9500, "lon": 29.0167, "kind": "district", "parent_code": "matabeleland_south"},
    {"code": "plumtree", "name": "Plumtree", "lat": -20.4833, "lon": 27.8167, "kind": "district", "parent_code": "matabeleland_south"},
    {"code": "beitbridge", "name": "Beitbridge", "lat": -22.2167, "lon": 30.0000, "kind": "district", "parent_code": "matabeleland_south"},
]

ZIMBABWE_REGIONS: list[dict[str, Any]] = [*_PROVINCES, *_DISTRICTS]

_REGION_BY_CODE = {r["code"]: r for r in ZIMBABWE_REGIONS}


def get_region(code: str | None) -> dict[str, Any] | None:
    if not code:
        return None
    return _REGION_BY_CODE.get(code.strip().lower())


def match_region_from_district(district: str | None) -> dict[str, Any] | None:
    """Match farm.district (free text) to a district or province entry."""
    if not district:
        return None
    raw_l = district.strip().lower()
    d = raw_l.replace(" ", "_")
    hit = _REGION_BY_CODE.get(d)
    if hit:
        return hit
    # Longest district name first to prefer "victoria falls" over "falls"
    for r in sorted(_DISTRICTS, key=lambda x: -len(x["name"])):
        name_l = r["name"].lower()
        code_l = r["code"].lower()
        if name_l in raw_l or code_l == d or code_l in raw_l.replace("-", "_"):
            return r
    aliases = {
        "vic falls": "victoria_falls",
        "vic_falls": "victoria_falls",
        "vf": "victoria_falls",
    }
    for k, v in aliases.items():
        if k in raw_l:
            return get_region(v)
    return None


def match_region_from_province(province: str | None) -> dict[str, Any] | None:
    """Best-effort match from free-text farm.province to a province entry."""
    if not province:
        return None
    p = province.lower().strip().replace(" ", "_")
    for r in _PROVINCES:
        if r["code"] in p or p in r["code"].replace("_", " "):
            return r
        if r["name"].lower() in province.lower():
            return r
    tokens = ("manicaland", "mashonaland", "masvingo", "matabeleland", "midlands", "harare", "bulawayo")
    for t in tokens:
        if t in p:
            if t == "mashonaland":
                if "central" in p:
                    return get_region("mashonaland_central")
                if "east" in p:
                    return get_region("mashonaland_east")
                if "west" in p:
                    return get_region("mashonaland_west")
                return get_region("mashonaland_east")
            if t == "matabeleland":
                if "north" in p:
                    return get_region("matabeleland_north")
                if "south" in p:
                    return get_region("matabeleland_south")
                return get_region("matabeleland_north")
            return get_region(t)
    return None
