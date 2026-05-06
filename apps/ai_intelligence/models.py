from __future__ import annotations

from django.conf import settings
from django.db import models

from apps.common.enums import (
    AnomalyAlertStatus,
    AnomalyAlertType,
    AnomalyEvidenceType,
    AnomalySeverity,
    ForecastModelType,
    ForecastRunStatus,
    ForecastSubjectType,
    ReviewLabelChoice,
    UserRole,
)
from apps.common.models import BaseModel
from apps.documents.models import Document
from apps.farms.models import Farm
from apps.lots.models import Lot
from apps.organizations.models import Organization
from apps.seasons.models import Season
from apps.settlements.models import Settlement


class ForecastRun(BaseModel):
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="forecast_runs",
        db_index=True,
    )
    model_type = models.CharField(max_length=20, choices=ForecastModelType.choices, db_index=True)
    model_version = models.CharField(max_length=64, db_index=True)
    trained_at = models.DateTimeField(null=True, blank=True)
    metrics_json = models.JSONField(default=dict, blank=True)
    status = models.CharField(
        max_length=20,
        choices=ForecastRunStatus.choices,
        default=ForecastRunStatus.PENDING,
        db_index=True,
    )
    summary_why = models.TextField(blank=True, default="", help_text="Human-readable explainability summary")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="forecast_runs_created",
    )

    class Meta:
        db_table = "ai_intelligence_forecast_run"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["organization", "model_type", "status"]),
        ]


class ForecastPoint(BaseModel):
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="forecast_points",
        db_index=True,
    )
    subject_type = models.CharField(max_length=20, choices=ForecastSubjectType.choices, db_index=True)
    subject_id = models.UUIDField(null=True, blank=True, db_index=True)
    region_code = models.CharField(max_length=64, blank=True, default="", db_index=True)
    season = models.ForeignKey(
        Season,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="forecast_points",
    )
    point_timestamp = models.DateTimeField(db_index=True)
    yhat = models.DecimalField(max_digits=14, decimal_places=4)
    yhat_lower = models.DecimalField(max_digits=14, decimal_places=4)
    yhat_upper = models.DecimalField(max_digits=14, decimal_places=4)
    model_version = models.CharField(max_length=64, db_index=True)
    explain_summary = models.TextField(blank=True, default="")

    class Meta:
        db_table = "ai_intelligence_forecast_point"
        ordering = ["-point_timestamp"]
        indexes = [
            models.Index(fields=["organization", "subject_type", "subject_id"]),
            models.Index(fields=["organization", "season_id"]),
        ]


class AnomalyAlert(BaseModel):
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="anomaly_alerts",
        db_index=True,
    )
    alert_type = models.CharField(max_length=64, choices=AnomalyAlertType.choices, db_index=True)
    severity = models.CharField(max_length=20, choices=AnomalySeverity.choices, db_index=True)
    score = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    status = models.CharField(
        max_length=20,
        choices=AnomalyAlertStatus.choices,
        default=AnomalyAlertStatus.OPEN,
        db_index=True,
    )
    lot = models.ForeignKey(Lot, on_delete=models.CASCADE, null=True, blank=True, related_name="anomaly_alerts")
    farm = models.ForeignKey(Farm, on_delete=models.CASCADE, null=True, blank=True, related_name="anomaly_alerts")
    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="anomaly_alerts",
    )
    settlement = models.ForeignKey(
        Settlement,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="anomaly_alerts",
    )
    detected_at = models.DateTimeField(db_index=True)
    model_version = models.CharField(max_length=64, blank=True, default="")
    title = models.CharField(max_length=255, blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="anomaly_alerts_created",
    )

    class Meta:
        db_table = "ai_intelligence_anomaly_alert"
        ordering = ["-detected_at"]
        indexes = [
            models.Index(fields=["organization", "status", "severity"]),
            models.Index(fields=["organization", "alert_type"]),
        ]


class AnomalyEvidence(BaseModel):
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="anomaly_evidence",
        db_index=True,
    )
    alert = models.ForeignKey(AnomalyAlert, on_delete=models.CASCADE, related_name="evidence_items")
    evidence_type = models.CharField(max_length=32, choices=AnomalyEvidenceType.choices, db_index=True)
    payload_json = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "ai_intelligence_anomaly_evidence"
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["organization", "alert"]),
        ]


class ReviewLabel(BaseModel):
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="anomaly_review_labels",
        db_index=True,
    )
    alert = models.ForeignKey(AnomalyAlert, on_delete=models.CASCADE, related_name="review_labels")
    label = models.CharField(max_length=32, choices=ReviewLabelChoice.choices, db_index=True)
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="anomaly_review_labels",
    )
    notes = models.TextField(blank=True, default="")

    class Meta:
        db_table = "ai_intelligence_review_label"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["organization", "alert"]),
        ]


class EvaluationMetricRun(BaseModel):
    """Offline / batch metrics (e.g. AUROC, MAPE) per org and model version."""

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="evaluation_metric_runs",
        db_index=True,
    )
    metric_name = models.CharField(max_length=64, db_index=True)
    model_key = models.CharField(max_length=64, db_index=True)
    model_version = models.CharField(max_length=64, blank=True, default="")
    value = models.DecimalField(max_digits=12, decimal_places=6, null=True, blank=True)
    metrics_json = models.JSONField(default=dict, blank=True)
    evaluated_at = models.DateTimeField(db_index=True)
    notes = models.TextField(blank=True, default="")

    class Meta:
        db_table = "ai_intelligence_evaluation_metric_run"
        ordering = ["-evaluated_at"]
        indexes = [
            models.Index(fields=["organization", "metric_name"]),
        ]


class AssistantConversation(BaseModel):
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="assistant_conversations",
        db_index=True,
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="assistant_conversations",
    )
    role_snapshot = models.CharField(max_length=32, choices=UserRole.choices)
    messages_json = models.JSONField(default=list, blank=True)

    class Meta:
        db_table = "ai_intelligence_assistant_conversation"
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["organization", "user"]),
        ]


class AssistantAuditLog(BaseModel):
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="assistant_audit_logs",
        db_index=True,
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="assistant_audit_logs",
    )
    role_snapshot = models.CharField(max_length=32, choices=UserRole.choices, blank=True, default="")
    tool_name = models.CharField(max_length=128, db_index=True)
    request_meta_json = models.JSONField(default=dict, blank=True)
    response_meta_json = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "ai_intelligence_assistant_audit_log"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["organization", "user"]),
            models.Index(fields=["organization", "tool_name"]),
        ]
