from django.contrib import admin

from apps.ai_intelligence.models import (
    AnomalyAlert,
    AnomalyEvidence,
    AssistantAuditLog,
    AssistantConversation,
    EvaluationMetricRun,
    ForecastPoint,
    ForecastRun,
    ReviewLabel,
)


@admin.register(ForecastRun)
class ForecastRunAdmin(admin.ModelAdmin):
    list_display = ("id", "organization", "model_type", "model_version", "status", "created_at")
    list_filter = ("model_type", "status")
    search_fields = ("model_version",)


@admin.register(ForecastPoint)
class ForecastPointAdmin(admin.ModelAdmin):
    list_display = ("id", "organization", "subject_type", "subject_id", "point_timestamp", "model_version")
    list_filter = ("subject_type",)


@admin.register(AnomalyAlert)
class AnomalyAlertAdmin(admin.ModelAdmin):
    list_display = ("id", "organization", "alert_type", "severity", "status", "detected_at")
    list_filter = ("alert_type", "severity", "status")


@admin.register(AnomalyEvidence)
class AnomalyEvidenceAdmin(admin.ModelAdmin):
    list_display = ("id", "alert", "evidence_type", "created_at")


@admin.register(ReviewLabel)
class ReviewLabelAdmin(admin.ModelAdmin):
    list_display = ("id", "alert", "label", "reviewer", "created_at")


@admin.register(EvaluationMetricRun)
class EvaluationMetricRunAdmin(admin.ModelAdmin):
    list_display = ("id", "metric_name", "model_key", "value", "evaluated_at")


@admin.register(AssistantConversation)
class AssistantConversationAdmin(admin.ModelAdmin):
    list_display = ("id", "organization", "user", "role_snapshot", "updated_at")


@admin.register(AssistantAuditLog)
class AssistantAuditLogAdmin(admin.ModelAdmin):
    list_display = ("id", "organization", "user", "tool_name", "created_at")
