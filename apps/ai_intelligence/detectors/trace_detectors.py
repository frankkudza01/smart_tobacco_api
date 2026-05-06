from __future__ import annotations

import logging
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from apps.ai_intelligence.models import AnomalyAlert, AnomalyEvidence
from apps.common.enums import (
    AnomalyAlertStatus,
    AnomalyAlertType,
    AnomalyEvidenceType,
    AnomalySeverity,
    TraceEventType,
)
from apps.lots.models import Lot
from apps.traceability.models import TraceEvent

logger = logging.getLogger(__name__)

MODEL_VERSION = "trace-detect-v1"
EXPECTED_FLOW = [
    TraceEventType.PLANTING,
    TraceEventType.HARVESTING,
    TraceEventType.GRADING,
    TraceEventType.SALE,
]


def run_all(organization) -> int:
    n = 0
    lots = Lot.objects.filter(farm__organization=organization).select_related(
        "season", "farm", "farm__organization"
    )
    for lot in lots:
        if not lot.farm.organization_id:
            continue
        n += _missing_events(lot)
        n += _sequence_break(lot)
        n += _time_delta_outlier(lot)
    return n


def _missing_events(lot: Lot) -> int:
    types = set(TraceEvent.objects.filter(lot=lot).values_list("event_type", flat=True))
    missing = [e for e in EXPECTED_FLOW if e not in types]
    if not missing:
        return 0
    if AnomalyAlert.objects.filter(
        organization=lot.farm.organization,
        alert_type=AnomalyAlertType.EVENT_MISSING,
        lot=lot,
        title__startswith="Missing trace events",
    ).exists():
        return 0
    alert = AnomalyAlert.objects.create(
        organization=lot.farm.organization,
        alert_type=AnomalyAlertType.EVENT_MISSING,
        severity=AnomalySeverity.MEDIUM,
        score=Decimal(str(len(missing) / len(EXPECTED_FLOW))),
        status=AnomalyAlertStatus.OPEN,
        lot=lot,
        farm=lot.farm,
        detected_at=timezone.now(),
        model_version=MODEL_VERSION,
        title="Missing trace events for lot",
    )
    AnomalyEvidence.objects.create(
        organization=alert.organization,
        alert=alert,
        evidence_type=AnomalyEvidenceType.RULE_VIOLATION,
        payload_json={"missing_event_types": missing},
    )
    return 1


def _sequence_break(lot: Lot) -> int:
    events = list(TraceEvent.objects.filter(lot=lot).order_by("timestamp"))
    if len(events) < 2:
        return 0
    order_index = {t: i for i, t in enumerate(EXPECTED_FLOW)}
    last_idx = -1
    for ev in events:
        idx = order_index.get(ev.event_type, -1)
        if idx == -1:
            continue
        if idx < last_idx:
            if AnomalyAlert.objects.filter(
                organization=lot.farm.organization,
                alert_type=AnomalyAlertType.EVENT_SEQUENCE_BREAK,
                lot=lot,
            ).exists():
                return 0
            alert = AnomalyAlert.objects.create(
                organization=lot.farm.organization,
                alert_type=AnomalyAlertType.EVENT_SEQUENCE_BREAK,
                severity=AnomalySeverity.HIGH,
                score=Decimal("0.9"),
                status=AnomalyAlertStatus.OPEN,
                lot=lot,
                farm=lot.farm,
                detected_at=timezone.now(),
                model_version=MODEL_VERSION,
                title="Out-of-order trace events",
            )
            AnomalyEvidence.objects.create(
                organization=alert.organization,
                alert=alert,
                evidence_type=AnomalyEvidenceType.SEQUENCE_BREAK,
                payload_json={
                    "event_id": str(ev.id),
                    "event_type": ev.event_type,
                    "previous_expected_index": last_idx,
                    "current_index": idx,
                },
            )
            return 1
        last_idx = max(last_idx, idx)
    return 0


def _time_delta_outlier(lot: Lot) -> int:
    events = list(TraceEvent.objects.filter(lot=lot).order_by("timestamp"))
    if len(events) < 2:
        return 0
    for a, b in zip(events, events[1:]):
        delta = b.timestamp - a.timestamp
        if delta < timedelta(minutes=1) or delta > timedelta(days=400):
            if AnomalyAlert.objects.filter(
                organization=lot.farm.organization,
                alert_type=AnomalyAlertType.EVENT_TIME_DELTA_OUTLIER,
                lot=lot,
            ).exists():
                return 0
            alert = AnomalyAlert.objects.create(
                organization=lot.farm.organization,
                alert_type=AnomalyAlertType.EVENT_TIME_DELTA_OUTLIER,
                severity=AnomalySeverity.LOW,
                score=Decimal("0.5"),
                status=AnomalyAlertStatus.OPEN,
                lot=lot,
                farm=lot.farm,
                detected_at=timezone.now(),
                model_version=MODEL_VERSION,
                title="Unusual time delta between trace events",
            )
            AnomalyEvidence.objects.create(
                organization=alert.organization,
                alert=alert,
                evidence_type=AnomalyEvidenceType.STAT_OUTLIER,
                payload_json={
                    "from_event": str(a.id),
                    "to_event": str(b.id),
                    "delta_seconds": delta.total_seconds(),
                },
            )
            return 1
    return 0
