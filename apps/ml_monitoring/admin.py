from django.contrib import admin

from apps.ml_monitoring.models import DailyMetrics, DriftMetrics, ModelRun


@admin.register(ModelRun)
class ModelRunAdmin(admin.ModelAdmin):
    list_display = ("organization", "model_type", "model_version", "created_at")


@admin.register(DailyMetrics)
class DailyMetricsAdmin(admin.ModelAdmin):
    list_display = ("organization", "date", "mape_yield", "alert_volume")


@admin.register(DriftMetrics)
class DriftMetricsAdmin(admin.ModelAdmin):
    list_display = ("organization", "date", "triggered")
