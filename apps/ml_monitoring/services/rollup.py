from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.utils import timezone

from apps.ai_intelligence.models import AnomalyAlert, EvaluationMetricRun, ForecastRun
from apps.ml_monitoring.models import DailyMetrics, DriftMetrics
from apps.ml_monitoring.services.drift_compute import compute_drift_for_org, should_trigger_retrain


def rollup_daily_metrics_for_org(organization, on_date: date | None = None) -> DailyMetrics:
    on_date = on_date or timezone.now().date()
    from apps.common.enums import AnomalyAlertStatus, ForecastRunStatus, ReviewLabelChoice
    from apps.ai_intelligence.models import ReviewLabel

    fr = (
        ForecastRun.objects.filter(organization=organization, status=ForecastRunStatus.COMPLETED)
        .order_by("-created_at")
        .first()
    )
    mape_yield = None
    mape_price = None
    if fr and fr.metrics_json:
        mape_yield = Decimal(str(fr.metrics_json.get("MAPE", 0.12)))

    ev = EvaluationMetricRun.objects.filter(
        organization=organization, metric_name="AUROC_ANOMALY", evaluated_at__date=on_date
    ).first()
    auroc = ev.value if ev else None

    labels = ReviewLabel.objects.filter(organization=organization, created_at__date=on_date)
    tp = labels.filter(label=ReviewLabelChoice.CONFIRMED).count()
    fp = labels.filter(label=ReviewLabelChoice.FALSE_POSITIVE).count()
    prec = Decimal(tp) / Decimal(tp + fp) if (tp + fp) else None
    rec = None

    alerts = AnomalyAlert.objects.filter(organization=organization, detected_at__date=on_date)
    vol = alerts.count()

    dm, _ = DailyMetrics.objects.update_or_create(
        organization=organization,
        date=on_date,
        defaults={
            "mape_yield": mape_yield,
            "mape_price": mape_price,
            "auroc_anomaly": auroc,
            "precision_dup": prec,
            "recall_dup": rec,
            "alert_volume": vol,
            "false_positive_rate": Decimal(fp) / Decimal(vol) if vol else None,
            "extra_json": {},
        },
    )

    baseline = list(
        DailyMetrics.objects.filter(organization=organization, date__lt=on_date)
        .order_by("-date")[:14]
        .values_list("mape_yield", flat=True)
    )
    baseline_f = [float(x) for x in baseline if x is not None]
    recent_f = [float(mape_yield)] if mape_yield is not None else []
    drift_payload = {}
    triggered = False
    reason = ""
    if baseline_f and recent_f:
        drift_payload = compute_drift_for_org(
            organization=organization, baseline_values=baseline_f, recent_values=recent_f * 7
        )
        triggered = drift_payload.get("triggered", False) or should_trigger_retrain(mape_yield=mape_yield)
        reason = drift_payload.get("reason", "") or ("mape_threshold" if should_trigger_retrain(mape_yield=mape_yield) else "")

    DriftMetrics.objects.update_or_create(
        organization=organization,
        date=on_date,
        defaults={
            "feature_drift_json": drift_payload,
            "outcome_drift_json": {"mape_yield": str(mape_yield) if mape_yield else None},
            "triggered": triggered,
            "reason": reason[:500],
        },
    )

    if triggered:
        from apps.notifications.services import create_notification
        from apps.common.enums import NotificationType, UserRole
        from apps.organizations.models import OrganizationMembership

        for m in OrganizationMembership.objects.filter(
            organization=organization,
            is_active=True,
            role__in=[UserRole.SYSTEM_ADMIN, UserRole.REGULATOR_AUDITOR],
        ).select_related("user"):
            create_notification(
                recipient=m.user,
                notification_type=NotificationType.SYSTEM,
                title="Model drift / retrain signal",
                body="Review monitoring dashboard; automated retrain may be required.",
                reference_type="drift",
                reference_id=organization.id,
            )

    return dm
