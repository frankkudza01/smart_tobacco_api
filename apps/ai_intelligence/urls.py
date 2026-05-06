from django.urls import path

from apps.ai_assistant.views import AIQueryView
from apps.ai_intelligence.views import (
    AIEvaluationSummaryView,
    AIHealthView,
    AnomalyCaseView,
    AnomalyExportDownloadView,
    AnomalyExportTokenView,
    AnomalyLabelView,
    AnomalyListView,
    AnomalyRunView,
    AssistantChatView,
    AssistantLeafDiagnoseView,
    DuplicateLabelsExportView,
    EvaluationMetricIngestView,
    ForecastPriceView,
    ForecastRetrainView,
    ForecastYieldView,
    SatelliteYieldOutlookView,
)

urlpatterns = [
    path("query/", AIQueryView.as_view(), name="ai-query"),
    path("assistant/chat/", AssistantChatView.as_view(), name="ai-assistant-chat"),
    path("assistant/diagnose-leaf/", AssistantLeafDiagnoseView.as_view(), name="ai-assistant-diagnose-leaf"),
    path("health/", AIHealthView.as_view(), name="ai-health"),
    path("health/evaluation/", AIEvaluationSummaryView.as_view(), name="ai-health-evaluation"),
    path("forecasts/yield/", ForecastYieldView.as_view(), name="ai-forecast-yield"),
    path(
        "forecasts/yield/satellite-outlook/",
        SatelliteYieldOutlookView.as_view(),
        name="ai-forecast-yield-satellite-outlook",
    ),
    path("forecasts/price/", ForecastPriceView.as_view(), name="ai-forecast-price"),
    path("forecasts/retrain/", ForecastRetrainView.as_view(), name="ai-forecast-retrain"),
    path("anomalies/", AnomalyListView.as_view(), name="ai-anomaly-list"),
    path("anomalies/run/", AnomalyRunView.as_view(), name="ai-anomaly-run"),
    path("anomalies/<uuid:alert_id>/label/", AnomalyLabelView.as_view(), name="ai-anomaly-label"),
    path("anomalies/<uuid:alert_id>/case/", AnomalyCaseView.as_view(), name="ai-anomaly-case"),
    path(
        "anomalies/<uuid:alert_id>/export-link/",
        AnomalyExportTokenView.as_view(),
        name="ai-anomaly-export-link",
    ),
    path(
        "exports/anomaly/",
        AnomalyExportDownloadView.as_view(),
        name="ai-anomaly-export-download",
    ),
    path("metrics/evaluation/", EvaluationMetricIngestView.as_view(), name="ai-evaluation-metrics"),
    path(
        "analytics/anomalies/duplicates/export-labels/",
        DuplicateLabelsExportView.as_view(),
        name="ai-duplicate-labels-export",
    ),
]
