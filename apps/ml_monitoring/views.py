from datetime import datetime

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.ai_intelligence.models import ForecastRun
from apps.common.enums import UserRole
from apps.common.org_utils import require_organization
from apps.common.schema import EmptySchemaSerializer
from apps.ml_monitoring.models import DailyMetrics, DriftMetrics, ModelRun


class IsAuditorOrAdmin(BasePermission):
    def has_permission(self, request, view):
        u = request.user
        return bool(u and u.is_authenticated and u.role in (UserRole.REGULATOR_AUDITOR, UserRole.SYSTEM_ADMIN))


@extend_schema(
    tags=["monitoring"],
    parameters=[
        OpenApiParameter("from", str, required=False),
        OpenApiParameter("to", str, required=False),
    ],
)
class MonitoringMetricsView(APIView):
    permission_classes = [IsAuthenticated, IsAuditorOrAdmin]
    serializer_class = EmptySchemaSerializer

    def get(self, request):
        org = require_organization(request.user)
        qs = DailyMetrics.objects.filter(organization=org)
        p_from = request.query_params.get("from")
        p_to = request.query_params.get("to")
        if p_from:
            qs = qs.filter(date__gte=p_from)
        if p_to:
            qs = qs.filter(date__lte=p_to)
        data = [
            {
                "date": str(r.date),
                "mape_yield": str(r.mape_yield) if r.mape_yield else None,
                "mape_price": str(r.mape_price) if r.mape_price else None,
                "auroc_anomaly": str(r.auroc_anomaly) if r.auroc_anomaly else None,
                "precision_dup": str(r.precision_dup) if r.precision_dup else None,
                "recall_dup": str(r.recall_dup) if r.recall_dup else None,
                "alert_volume": r.alert_volume,
                "false_positive_rate": str(r.false_positive_rate) if r.false_positive_rate else None,
            }
            for r in qs.order_by("-date")[:366]
        ]
        return Response({"results": data})


@extend_schema(tags=["monitoring"])
class MonitoringDriftView(APIView):
    permission_classes = [IsAuthenticated, IsAuditorOrAdmin]
    serializer_class = EmptySchemaSerializer

    def get(self, request):
        org = require_organization(request.user)
        qs = DriftMetrics.objects.filter(organization=org)
        if request.query_params.get("from"):
            qs = qs.filter(date__gte=request.query_params.get("from"))
        if request.query_params.get("to"):
            qs = qs.filter(date__lte=request.query_params.get("to"))
        data = [
            {
                "date": str(r.date),
                "triggered": r.triggered,
                "reason": r.reason,
                "feature_drift": r.feature_drift_json,
                "outcome_drift": r.outcome_drift_json,
            }
            for r in qs.order_by("-date")[:366]
        ]
        return Response({"results": data})


@extend_schema(tags=["monitoring"])
class MonitoringRetrainHistoryView(APIView):
    permission_classes = [IsAuthenticated, IsAuditorOrAdmin]
    serializer_class = EmptySchemaSerializer

    def get(self, request):
        org = require_organization(request.user)
        runs = ForecastRun.objects.filter(organization=org).order_by("-created_at")[:100]
        data = [
            {
                "id": str(r.id),
                "model_type": r.model_type,
                "model_version": r.model_version,
                "status": r.status,
                "metrics": r.metrics_json,
                "trained_at": r.trained_at.isoformat() if r.trained_at else None,
            }
            for r in runs
        ]
        return Response({"results": data})


@extend_schema(tags=["monitoring"])
class MonitoringSummaryLiteView(APIView):
    """Farmers/buyers: non-sensitive headline only."""

    permission_classes = [IsAuthenticated]
    serializer_class = EmptySchemaSerializer

    def get(self, request):
        org = require_organization(request.user)
        if request.user.role in (UserRole.REGULATOR_AUDITOR, UserRole.SYSTEM_ADMIN):
            return Response(
                {"status": "ok", "headline": "Use /monitoring/metrics/ for full detail."},
            )
        latest = DailyMetrics.objects.filter(organization=org).order_by("-date").first()
        if not latest:
            return Response({"status": "ok", "headline": "No metrics yet."})
        return Response(
            {
                "status": "ok",
                "headline": "Platform models are monitored. Contact support for details.",
                "last_updated": str(latest.date),
            }
        )
