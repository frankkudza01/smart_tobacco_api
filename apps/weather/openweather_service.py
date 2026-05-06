"""
OpenWeatherMap 2.5: current weather + 5-day / 3-hour forecast (metric).

API key must be set in OPENWEATHERMAP_API_KEY — never commit keys to the repo.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

OWM_CURRENT = "https://api.openweathermap.org/data/2.5/weather"
OWM_FORECAST = "https://api.openweathermap.org/data/2.5/forecast"


def _api_key() -> str:
    return (getattr(settings, "OPENWEATHERMAP_API_KEY", "") or "").strip()


def fetch_current_and_forecast(*, lat: float, lon: float) -> dict[str, Any]:
    key = _api_key()
    if not key:
        raise RuntimeError("OPENWEATHERMAP_API_KEY is not configured.")

    timeout = getattr(settings, "OPENWEATHERMAP_TIMEOUT_SECONDS", 15)
    params = {"lat": lat, "lon": lon, "appid": key, "units": "metric"}

    cur = requests.get(OWM_CURRENT, params=params, timeout=timeout)
    cur.raise_for_status()
    current = cur.json()

    fc = requests.get(OWM_FORECAST, params=params, timeout=timeout)
    fc.raise_for_status()
    forecast = fc.json()

    return {"current": current, "forecast": forecast}


def _slot_rain_mm(slot: dict[str, Any]) -> float:
    rain = slot.get("rain") or {}
    if isinstance(rain, dict):
        return float(rain.get("3h") or 0)
    return 0.0


def _aggregate_forecast(forecast: dict[str, Any], hours: int) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    end = now + timedelta(hours=hours)
    slots_out: list[dict[str, Any]] = []
    total_rain = 0.0
    temps: list[float] = []

    for item in forecast.get("list") or []:
        dt_unix = item.get("dt")
        if dt_unix is None:
            continue
        t = datetime.fromtimestamp(int(dt_unix), tz=timezone.utc)
        if t > end:
            break
        if t < now:
            continue
        r = _slot_rain_mm(item)
        total_rain += r
        main = item.get("main") or {}
        if "temp" in main:
            temps.append(float(main["temp"]))
        w = (item.get("weather") or [{}])[0]
        slots_out.append(
            {
                "dt_utc": t.isoformat(),
                "temp_c": main.get("temp"),
                "rain_next_interval_mm": round(r, 2) if r else 0,
                "description": w.get("description"),
            }
        )

    return {
        "hours": hours,
        "total_rain_mm": round(total_rain, 2),
        "max_temp_c": round(max(temps), 1) if temps else None,
        "min_temp_c": round(min(temps), 1) if temps else None,
        "slots": slots_out[:16],
    }


def _current_summary(current: dict[str, Any]) -> dict[str, Any]:
    main = current.get("main") or {}
    w = (current.get("weather") or [{}])[0]
    rain_1h = 0.0
    if "rain" in current and isinstance(current["rain"], dict):
        rain_1h = float(current["rain"].get("1h") or 0)
    return {
        "temp_c": main.get("temp"),
        "feels_like_c": main.get("feels_like"),
        "humidity_pct": main.get("humidity"),
        "description": w.get("description"),
        "rain_last_1h_mm": round(rain_1h, 2),
    }


def irrigation_advice(*, rain_24h_mm: float, rain_48h_mm: float) -> dict[str, Any]:
    """Simple rule-based copy for smallholders (not agronomic advice)."""
    if rain_24h_mm >= 10:
        return {
            "headline": "Rain likely in the next 24 hours",
            "detail": (
                f"About {rain_24h_mm:.0f} mm of rain is expected in the next 24 hours. "
                "You may not need to irrigate tomorrow — check field conditions and local forecasts."
            ),
            "severity": "info",
        }
    if rain_24h_mm >= 5:
        return {
            "headline": "Some rain expected (24 h)",
            "detail": (
                f"Roughly {rain_24h_mm:.0f} mm may fall in the next day. "
                "Consider delaying irrigation unless soils are already dry."
            ),
            "severity": "info",
        }
    if rain_48h_mm >= 15:
        return {
            "headline": "Wetter pattern in the next two days",
            "detail": (
                f"About {rain_48h_mm:.0f} mm may accumulate within 48 hours. "
                "Plan irrigation carefully."
            ),
            "severity": "info",
        }
    return {
        "headline": "Little rain in the forecast window",
        "detail": (
            "Little meaningful rain is expected in the next 48 hours. "
            "Monitor soil moisture and irrigate if your crop needs water."
        ),
        "severity": "neutral",
    }


def build_farmer_payload(
    *,
    region_code: str | None,
    region_name: str | None,
    lat: float,
    lon: float,
    location_kind: str | None = None,
    parent_region_code: str | None = None,
) -> dict[str, Any]:
    raw = fetch_current_and_forecast(lat=lat, lon=lon)
    current = raw["current"]
    forecast = raw["forecast"]

    agg24 = _aggregate_forecast(forecast, 24)
    agg48 = _aggregate_forecast(forecast, 48)
    advice = irrigation_advice(
        rain_24h_mm=float(agg24["total_rain_mm"] or 0),
        rain_48h_mm=float(agg48["total_rain_mm"] or 0),
    )

    city = (forecast.get("city") or {}).get("name")

    alias = (getattr(settings, "OPENWEATHERMAP_KEY_NAME", "") or "").strip() or None

    return {
        "location": {
            "region_code": region_code,
            "region_name": region_name,
            "lat": lat,
            "lon": lon,
            "openweather_city": city,
            "kind": location_kind,
            "parent_region_code": parent_region_code,
        },
        "current": _current_summary(current),
        "forecast_next_24h": agg24,
        "forecast_next_48h": agg48,
        "irrigation_advice": advice,
        "source": "OpenWeatherMap",
        "api_key_alias": alias,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }
