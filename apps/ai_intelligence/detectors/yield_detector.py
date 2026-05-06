from __future__ import annotations

import logging
from decimal import Decimal

from django.utils import timezone

from apps.ai_intelligence.models import AnomalyAlert, AnomalyEvidence, ForecastPoint
from apps.common.enums import (
    AnomalyAlertStatus,
    AnomalyAlertType,
    AnomalyEvidenceType,
    AnomalySeverity,
    ForecastSubjectType,
)
from apps.seasons.models import FarmSeasonAssociation

logger = logging.getLogger(__name__)

MODEL_VERSION = "yield-detect-v1"


def run_all(organization) -> int:
    created = 0
    qs = FarmSeasonAssociation.objects.filter(farm__organization=organization).select_related(
        "farm", "season"
    )
    for assoc in qs:
        season = assoc.season
        farm = assoc.farm
        if season.actual_yield_kg is None:
            continue
        fp = (
            ForecastPoint.objects.filter(
                organization=organization,
                season=season,
                subject_type=ForecastSubjectType.FARM,
                subject_id=farm.id,
            )
            .order_by("-point_timestamp")
            .first()
        )
        if not fp:
            continue
        actual = season.actual_yield_kg
        if actual < fp.yhat_lower or actual > fp.yhat_upper:
            if AnomalyAlert.objects.filter(
                organization=organization,
                alert_type=AnomalyAlertType.YIELD_RESIDUAL_OUTLIER,
                farm=farm,
                title__startswith="Yield outside forecast",
            ).exists():
                continue
            alert = AnomalyAlert.objects.create(
                organization=organization,
                alert_type=AnomalyAlertType.YIELD_RESIDUAL_OUTLIER,
                severity=AnomalySeverity.MEDIUM,
                score=Decimal("0.8"),
                status=AnomalyAlertStatus.OPEN,
                farm=farm,
                detected_at=timezone.now(),
                model_version=MODEL_VERSION,
                title="Yield outside forecast interval",
            )
            AnomalyEvidence.objects.create(
                organization=organization,
                alert=alert,
                evidence_type=AnomalyEvidenceType.STAT_OUTLIER,
                payload_json={
                    "actual_yield_kg": str(actual),
                    "yhat": str(fp.yhat),
                    "yhat_lower": str(fp.yhat_lower),
                    "yhat_upper": str(fp.yhat_upper),
                    "season_id": str(season.id),
                    "farm_id": str(farm.id),
                },
            )
            created += 1
    return created
