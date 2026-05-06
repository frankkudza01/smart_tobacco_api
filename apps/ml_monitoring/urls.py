from django.urls import path

from apps.ml_monitoring.views import (
    MonitoringDriftView,
    MonitoringMetricsView,
    MonitoringRetrainHistoryView,
    MonitoringSummaryLiteView,
)

urlpatterns = [
    path("monitoring/metrics/", MonitoringMetricsView.as_view(), name="monitoring-metrics"),
    path("monitoring/drift/", MonitoringDriftView.as_view(), name="monitoring-drift"),
    path("monitoring/retrain/history/", MonitoringRetrainHistoryView.as_view(), name="monitoring-retrain-history"),
    path("monitoring/summary/", MonitoringSummaryLiteView.as_view(), name="monitoring-summary-lite"),
]
