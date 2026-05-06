from __future__ import annotations

from django.conf import settings
from django.db import models

from apps.common.enums import ModelRunKind
from apps.common.models import BaseModel
from apps.organizations.models import Organization


class ModelRun(BaseModel):
    """Unified training/inference run record (alongside ai_intelligence.ForecastRun)."""

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="model_runs",
        db_index=True,
    )
    model_type = models.CharField(max_length=32, choices=ModelRunKind.choices, db_index=True)
    model_version = models.CharField(max_length=64, db_index=True)
    trained_at = models.DateTimeField(null=True, blank=True)
    metrics_json = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="model_runs_created",
    )

    class Meta:
        db_table = "ml_monitoring_model_run"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["organization", "model_type"])]


class DailyMetrics(BaseModel):
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="daily_metrics",
        db_index=True,
    )
    date = models.DateField(db_index=True)
    mape_yield = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    mape_price = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    auroc_anomaly = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    precision_dup = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    recall_dup = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    alert_volume = models.PositiveIntegerField(default=0)
    false_positive_rate = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    extra_json = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "ml_monitoring_daily_metrics"
        unique_together = [["organization", "date"]]
        ordering = ["-date"]


class DriftMetrics(BaseModel):
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="drift_metrics",
        db_index=True,
    )
    date = models.DateField(db_index=True)
    feature_drift_json = models.JSONField(default=dict, blank=True)
    outcome_drift_json = models.JSONField(default=dict, blank=True)
    triggered = models.BooleanField(default=False, db_index=True)
    reason = models.CharField(max_length=500, blank=True, default="")

    class Meta:
        db_table = "ml_monitoring_drift_metrics"
        ordering = ["-date"]
        unique_together = [["organization", "date"]]
        indexes = [models.Index(fields=["organization", "triggered"])]
