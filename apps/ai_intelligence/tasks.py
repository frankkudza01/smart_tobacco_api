from __future__ import annotations

import logging

from celery import shared_task
from django.utils import timezone

from apps.ai_intelligence.detectors.runner import run_anomaly_detection
from apps.ai_intelligence.models import EvaluationMetricRun
from apps.ai_intelligence.services.forecast_service import ForecastService
from apps.common.enums import ForecastModelType
from apps.organizations.models import Organization

logger = logging.getLogger(__name__)


@shared_task(name="ai_intelligence.retrain_forecasts_job")
def retrain_forecasts_job(org_id: str, model_type: str = "yield") -> str:
    org = Organization.objects.get(id=org_id)
    run = ForecastService.run_retrain_mvp(organization=org, model_type=model_type, created_by=None)
    return str(run.id)


@shared_task(name="ai_intelligence.run_anomaly_detection_job")
def run_anomaly_detection_job(org_id: str, detection_types: list[str] | None = None) -> int:
    org = Organization.objects.get(id=org_id)
    return run_anomaly_detection(org, detection_types=detection_types)


@shared_task(name="ai_intelligence.record_evaluation_metric")
def record_evaluation_metric_job(
    org_id: str,
    metric_name: str,
    model_key: str,
    model_version: str = "",
    value: str | None = None,
    metrics_json: dict | None = None,
    notes: str = "",
) -> str:
    org = Organization.objects.get(id=org_id)
    from decimal import Decimal

    v = Decimal(value) if value is not None else None
    row = EvaluationMetricRun.objects.create(
        organization=org,
        metric_name=metric_name,
        model_key=model_key,
        model_version=model_version,
        value=v,
        metrics_json=metrics_json or {},
        evaluated_at=timezone.now(),
        notes=notes[:2000],
    )
    return str(row.id)
