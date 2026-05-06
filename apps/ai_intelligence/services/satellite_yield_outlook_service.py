"""
Farmer-facing satellite + vegetation yield outlook.

Combines NDVI time series from tobacco monitoring polygons with a transparent
heuristic band, then optionally asks the configured LLM to narrate steps and
a plain-language summary (agentic synthesis — numbers stay server-side).
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from apps.common.access import can_view_farm
from apps.farms.models import Farm
from apps.seasons.models import FarmSeasonAssociation, Season
from apps.tobacco_monitoring.models import CropStressEvent, MetricType, TobaccoFieldPolygon

logger = logging.getLogger(__name__)

MODEL_VERSION = "satellite-agent-v1"


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _baseline_kg_per_ha_from_season(season: Season | None, farm_ha: float) -> float:
    """Anchor on season expected total kg / farm hectares when plausible."""
    raw = getattr(settings, "TOBACCO_SATELLITE_YIELD_BASELINE_KG_HA", 1900.0)
    try:
        base = float(raw)
    except (TypeError, ValueError):
        base = 1900.0
    if season and season.expected_yield_kg and farm_ha > 0.05:
        try:
            per_ha = float(season.expected_yield_kg) / farm_ha
            if 400 <= per_ha <= 4500:
                return per_ha
        except Exception:
            pass
    return base


def _ndvi_factor(ndvi: float | None) -> float:
    if ndvi is None:
        return 0.92
    n = _clamp(float(ndvi), 0.08, 0.92)
    # Map healthy canopy NDVI into a mild multiplier around 1.0
    return _clamp(0.62 + (n - 0.25) * 0.72, 0.72, 1.18)


def build_satellite_yield_outlook(
    user,
    *,
    farm_id: UUID,
    season_id: UUID | None = None,
) -> dict[str, Any]:
    try:
        farm = Farm.objects.select_related("owner", "organization").get(id=farm_id)
    except Farm.DoesNotExist:
        return {"detail": "farm_not_found", "status_code": 404}

    if not can_view_farm(user, farm):
        return {"detail": "forbidden", "status_code": 403}

    season: Season | None = None
    if season_id:
        try:
            season = Season.objects.get(id=season_id)
        except Season.DoesNotExist:
            return {"detail": "season_not_found", "status_code": 404}
        linked = FarmSeasonAssociation.objects.filter(farm=farm, season=season).exists()
        if not linked:
            return {"detail": "season_not_linked_to_farm", "status_code": 400}

    poly_qs = TobaccoFieldPolygon.objects.filter(farm=farm, is_active=True)
    if season:
        poly_qs = poly_qs.filter(
            Q(season="") | Q(season__iexact=str(season.crop_year)),
        )

    polygons = list(poly_qs.only("id", "field_name", "area_hectares", "season", "monitoring_status"))

    farm_ha = float(farm.size_hectares or 0) or 0.0
    poly_ha_sum = sum(float(p.area_hectares or 0) for p in polygons)
    total_ha = farm_ha if farm_ha > 0 else poly_ha_sum
    if total_ha <= 0:
        total_ha = max(poly_ha_sum, 0.01)

    ndvi_values: list[tuple[float, date | None, str]] = []
    latest_ndvi_date: date | None = None
    for p in polygons:
        obs = (
            p.observations.filter(metric_type=MetricType.NDVI)
            .order_by("-observation_date")
            .values("metric_value", "observation_date")[:1]
        )
        row = obs.first()
        if row:
            v = float(row["metric_value"])
            d = row["observation_date"]
            ndvi_values.append((v, d, p.field_name))
            if d and (latest_ndvi_date is None or d > latest_ndvi_date):
                latest_ndvi_date = d

    ndvi_mean = sum(x[0] for x in ndvi_values) / len(ndvi_values) if ndvi_values else None

    p_ids = [p.id for p in polygons]
    stress_count = CropStressEvent.objects.filter(polygon_id__in=p_ids).count() if p_ids else 0

    baseline = _baseline_kg_per_ha_from_season(season, total_ha)
    factor = _ndvi_factor(ndvi_mean)
    yhat = baseline * factor
    band = 0.12 + (0.08 if ndvi_mean is None else 0.0)
    y_lo = yhat * (1.0 - band)
    y_hi = yhat * (1.0 + band)
    total_kg = yhat * total_ha

    # Confidence: data freshness, polygon coverage, NDVI presence
    conf = 52
    if polygons:
        conf += 10
    if ndvi_mean is not None:
        conf += 14
    if latest_ndvi_date:
        age = (timezone.now().date() - latest_ndvi_date).days
        if age <= 10:
            conf += 12
        elif age <= 24:
            conf += 6
        elif age > 38:
            conf -= 12
    if stress_count == 0:
        conf += 4
    else:
        conf -= min(12, stress_count * 2)
    conf = int(_clamp(conf, 28, 92))

    agent_steps: list[dict[str, str]] = [
        {
            "id": "context",
            "title": "Farm context",
            "detail": (
                f"{farm.name}: about {total_ha:.2f} ha under analysis"
                + (f" for crop year {season.crop_year}." if season else ".")
            ),
        },
        {
            "id": "satellite",
            "title": "Satellite field coverage",
            "detail": (
                f"{len(polygons)} monitoring field(s) linked"
                + (
                    f"; latest NDVI ≈ {ndvi_mean:.2f} on {latest_ndvi_date}."
                    if ndvi_mean is not None and latest_ndvi_date
                    else (
                        f"; latest NDVI ≈ {ndvi_mean:.2f}."
                        if ndvi_mean is not None
                        else ". No NDVI samples yet — estimate uses seasonal baseline only."
                    )
                )
            ),
        },
        {
            "id": "stress",
            "title": "Stress signals",
            "detail": (
                f"{stress_count} stress event(s) recorded on these polygons in the monitoring feed."
            ),
        },
        {
            "id": "blend",
            "title": "Yield blend (transparent)",
            "detail": (
                f"Heuristic: baseline ≈ {baseline:.0f} kg/ha from "
                f"{'season expected yield / hectares' if season and season.expected_yield_kg else 'regional defaults'}, "
                f"scaled by vegetation index (×{factor:.2f})."
            ),
        },
    ]

    summary_plain = (
        f"Outlook ≈ {yhat:.0f} kg per hectare (about {total_kg:,.0f} kg across {total_ha:.2f} ha). "
        f"{'Vegetation looks in line with the baseline.' if ndvi_mean and ndvi_mean >= 0.35 else 'Satellite vigor is thin or not yet available — treat this as early guidance.'} "
        f"Confidence is moderate ({conf}%): satellite yield models are indicative, not a contract grade."
    )

    ai_enhanced = False
    ai_enabled = bool(getattr(settings, "AI_ENABLED", False))
    if ai_enabled:
        from apps.ai_intelligence.services.openai_safe import chat_json_schema, has_provider_credentials

        if has_provider_credentials():
            schema = {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "summary_plain": {"type": "string"},
                    "agent_step_tweaks": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "id": {"type": "string"},
                                "title": {"type": "string"},
                                "detail": {"type": "string"},
                            },
                            "required": ["id", "title", "detail"],
                        },
                    },
                },
                "required": ["summary_plain", "agent_step_tweaks"],
            }
            facts = {
                "farm_name": farm.name,
                "total_ha": round(total_ha, 4),
                "polygon_count": len(polygons),
                "ndvi_mean": ndvi_mean,
                "latest_ndvi_date": str(latest_ndvi_date) if latest_ndvi_date else None,
                "stress_events": stress_count,
                "yhat_kg_per_ha": round(yhat, 2),
                "confidence_percent": conf,
                "crop_year": season.crop_year if season else None,
            }
            user_msg = (
                "You are an agronomy copilot for Zimbabwe tobacco smallholders. "
                "Given ONLY these JSON facts, write a short farmer-friendly summary (2–4 sentences). "
                "Do NOT invent new numbers; refer to the outlook qualitatively. "
                "Optionally refine titles/details for agent steps (same ids only: context, satellite, stress, blend). "
                f"FACTS_JSON: {facts}"
            )
            try:
                out = chat_json_schema(
                    system_prompt="Return concise JSON only. No markdown.",
                    user_message=user_msg,
                    json_schema_name="satellite_yield_outlook",
                    json_schema=schema,
                )
                summary_plain = (out.get("summary_plain") or summary_plain).strip()[:2400]
                tweaks = out.get("agent_step_tweaks") or []
                by_id = {s["id"]: s for s in agent_steps}
                for t in tweaks:
                    tid = (t.get("id") or "").strip()
                    if tid in by_id and t.get("title") and t.get("detail"):
                        by_id[tid]["title"] = str(t["title"])[:200]
                        by_id[tid]["detail"] = str(t["detail"])[:900]
                agent_steps = [by_id[k] for k in ("context", "satellite", "stress", "blend") if k in by_id]
                ai_enhanced = True
            except Exception:
                logger.exception("satellite_yield_outlook LLM synthesis failed; using heuristic copy")

    return {
        "farm_id": str(farm.id),
        "farm_name": farm.name,
        "season_id": str(season.id) if season else None,
        "crop_year": season.crop_year if season else None,
        "total_hectares": round(total_ha, 4),
        "polygon_count": len(polygons),
        "latest_ndvi_mean": round(ndvi_mean, 4) if ndvi_mean is not None else None,
        "latest_ndvi_date": latest_ndvi_date.isoformat() if latest_ndvi_date else None,
        "stress_event_count": stress_count,
        "yhat_kg_per_ha": round(yhat, 2),
        "yhat_lower_kg_per_ha": round(y_lo, 2),
        "yhat_upper_kg_per_ha": round(y_hi, 2),
        "total_estimate_kg": round(total_kg, 2),
        "confidence_percent": conf,
        "model_version": MODEL_VERSION,
        "agent_steps": agent_steps,
        "summary_plain": summary_plain,
        "ai_enhanced": ai_enhanced,
        "generated_at": timezone.now().isoformat(),
    }
