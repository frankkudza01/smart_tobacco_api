"""Simple buyer-side yield proxy from NDVI × hectares (tunable coefficient)."""

from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.db.models import Sum
from django.db.models.functions import Coalesce

from apps.common.enums import UserRole
from apps.tobacco_monitoring.models import (
    CropStressEvent,
    MetricType,
    PlantingVerificationStatus,
    TobaccoFieldPolygon,
)
from apps.tobacco_monitoring.services.access import polygons_visible_for_user


def buyer_monitoring_summary(user, *, season: str | None = None) -> dict:
    """
    Dashboard-style rollups for the authenticated buyer/admin scope.

    `expected_yield_proxy_tonnes` = coefficient × Σ(latest_ndvi × area_ha) (heuristic).
    """
    qs = polygons_visible_for_user(user).filter(is_active=True)
    if season:
        qs = qs.filter(season=season)

    polygons = list(qs.select_related("farm", "farm__owner"))
    coef = float(getattr(settings, "TOBACCO_YIELD_PROXY_COEFFICIENT", 0.25))

    total_ha = Decimal("0")
    planted_ha = Decimal("0")
    yield_acc = 0.0
    verification_counts: dict[str, int] = {}

    for p in polygons:
        ha = p.area_hectares or Decimal("0")
        total_ha += ha
        latest = (
            p.observations.filter(metric_type=MetricType.NDVI).order_by("-observation_date").first()
        )
        ndvi = float(latest.metric_value) if latest else 0.0
        yield_acc += coef * float(ha) * max(ndvi, 0.0)

        ver = p.planting_verifications.order_by("-assessed_at").first()
        if ver and ver.status in (
            PlantingVerificationStatus.ESTABLISHED,
            PlantingVerificationStatus.VERIFIED_PLANTED,
            PlantingVerificationStatus.PARTIALLY_ESTABLISHED,
        ):
            planted_ha += ha
        if ver:
            verification_counts[ver.status] = verification_counts.get(ver.status, 0) + 1

    p_ids = [x.id for x in polygons]
    stress_count = CropStressEvent.objects.filter(polygon_id__in=p_ids).count()

    by_province: dict[str, dict] = {}
    for p in polygons:
        prov = p.province or "Unknown"
        bucket = by_province.setdefault(
            prov,
            {"polygons": 0, "hectares": Decimal("0"), "stress_events": 0},
        )
        bucket["polygons"] += 1
        bucket["hectares"] += p.area_hectares or Decimal("0")

    for prov, bucket in by_province.items():
        bucket["hectares"] = float(bucket["hectares"])
        scoped_ids = [x.id for x in polygons if (x.province or "Unknown").lower() == prov.lower()]
        bucket["stress_events"] = CropStressEvent.objects.filter(polygon_id__in=scoped_ids).count()

    return {
        "total_contracted_polygons": len(polygons),
        "total_monitored_hectares": float(total_ha),
        "planted_verified_hectares_proxy": float(planted_ha),
        "stress_event_count": stress_count,
        "expected_yield_proxy_tonnes": round(yield_acc, 3),
        "yield_proxy_coefficient": coef,
        "by_province": by_province,
        "planting_verification_breakdown": verification_counts,
    }


def regional_summary(*, user=None, provinces: list[str] | None = None) -> dict:
    """
    Rollup for core tobacco provinces.

    Buyers only see polygons (and stress events) in their org scope; admins and
    auditors see national aggregates for supported provinces.
    """
    provs = provinces or list(getattr(settings, "TOBACCO_SUPPORTED_PROVINCES", []))
    role = getattr(user, "role", None) if user and user.is_authenticated else None

    if role == UserRole.BUYER_CONTRACTOR and user is not None:
        visible = polygons_visible_for_user(user).filter(is_active=True)
    else:
        visible = TobaccoFieldPolygon.objects.filter(is_active=True)

    out: dict[str, dict] = {}
    for raw_prov in provs:
        prov = (raw_prov or "").strip()
        if not prov:
            continue
        sub = visible.filter(province__iexact=prov)
        pids = sub.values_list("id", flat=True)
        out[prov] = {
            "polygon_count": sub.count(),
            "total_hectares": float(
                sub.aggregate(s=Coalesce(Sum("area_hectares"), Decimal("0")))["s"] or 0
            ),
            "stress_events": CropStressEvent.objects.filter(polygon_id__in=pids).count(),
        }
    return {"regions": out}
