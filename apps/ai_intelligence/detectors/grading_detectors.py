from __future__ import annotations

import logging
import re
from decimal import Decimal
from statistics import mean, pstdev

from django.utils import timezone

from apps.ai_intelligence.models import AnomalyAlert, AnomalyEvidence
from apps.common.enums import AnomalyAlertStatus, AnomalyAlertType, AnomalyEvidenceType, AnomalySeverity
from apps.grading.models import GradeRecord
from apps.lots.models import Lot
from apps.sales.models import Sale

logger = logging.getLogger(__name__)

MODEL_VERSION = "grading-detect-v1"


def _grade_numeric(grade: str) -> float | None:
    m = re.match(r"^(\d+)", (grade or "").strip())
    if not m:
        return None
    return float(m.group(1))


def run_all(organization) -> int:
    n = 0
    lots = Lot.objects.filter(farm__organization=organization).select_related("season", "farm")
    for lot in lots:
        n += _grade_jump(lot)
        n += _grade_price_mismatch(lot)
    return n


def _grade_jump(lot: Lot) -> int:
    farm = lot.farm
    org = farm.organization
    if not org:
        return 0
    history = GradeRecord.objects.filter(
        lot__farm=farm,
    ).exclude(lot=lot)
    nums = [_grade_numeric(g.grade) for g in history]
    nums = [x for x in nums if x is not None]
    current = GradeRecord.objects.filter(lot=lot).order_by("-graded_at").first()
    if not current:
        return 0
    cur = _grade_numeric(current.grade)
    if cur is None or len(nums) < 3:
        return 0
    mu = mean(nums)
    try:
        sd = pstdev(nums)
    except Exception:
        sd = 0.0
    if sd == 0:
        return 0
    z = (cur - mu) / sd
    if abs(z) < 2.5:
        return 0
    if AnomalyAlert.objects.filter(organization=org, alert_type=AnomalyAlertType.GRADE_JUMP, lot=lot).exists():
        return 0
    alert = AnomalyAlert.objects.create(
        organization=org,
        alert_type=AnomalyAlertType.GRADE_JUMP,
        severity=AnomalySeverity.MEDIUM,
        score=Decimal(str(round(abs(z) / 4, 4))),
        status=AnomalyAlertStatus.OPEN,
        lot=lot,
        farm=farm,
        detected_at=timezone.now(),
        model_version=MODEL_VERSION,
        title="Grade jump vs historical distribution",
    )
    AnomalyEvidence.objects.create(
        organization=org,
        alert=alert,
        evidence_type=AnomalyEvidenceType.STAT_OUTLIER,
        payload_json={"z_score": z, "current_grade": current.grade, "historical_mean": mu, "historical_stdev": sd},
    )
    return 1


def _grade_price_mismatch(lot: Lot) -> int:
    farm = lot.farm
    org = farm.organization
    if not org:
        return 0
    gr = GradeRecord.objects.filter(lot=lot).order_by("-graded_at").first()
    sale = Sale.objects.filter(lot=lot).order_by("-sale_date").first()
    if not gr or not sale:
        return 0
    # Simple expected price from grade numeric * baseline
    gn = _grade_numeric(gr.grade)
    if gn is None:
        return 0
    expected_pp = Decimal("0.5") * Decimal(str(gn))
    residual = abs(sale.price_per_kg - expected_pp)
    if residual <= Decimal("1.5"):
        return 0
    if AnomalyAlert.objects.filter(
        organization=org, alert_type=AnomalyAlertType.GRADE_PRICE_MISMATCH, lot=lot
    ).exists():
        return 0
    alert = AnomalyAlert.objects.create(
        organization=org,
        alert_type=AnomalyAlertType.GRADE_PRICE_MISMATCH,
        severity=AnomalySeverity.MEDIUM,
        score=Decimal(str(residual)),
        status=AnomalyAlertStatus.OPEN,
        lot=lot,
        farm=farm,
        detected_at=timezone.now(),
        model_version=MODEL_VERSION,
        title="Grade vs price residual high",
    )
    AnomalyEvidence.objects.create(
        organization=org,
        alert=alert,
        evidence_type=AnomalyEvidenceType.STAT_OUTLIER,
        payload_json={
            "grade": gr.grade,
            "price_per_kg": str(sale.price_per_kg),
            "expected_price_per_kg_heuristic": str(expected_pp),
            "residual": str(residual),
        },
    )
    return 1
