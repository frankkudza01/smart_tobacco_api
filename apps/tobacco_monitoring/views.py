from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.enums import UserRole
from apps.common.permissions import IsSmallholderFarmer
from apps.tobacco_monitoring.permissions import IsBuyerAdminOrAuditor
from apps.tobacco_monitoring.models import (
    CropStressEvent,
    MetricType,
    PlantingVerificationRecord,
    PolygonObservation,
    TobaccoFieldPolygon,
)
from apps.tobacco_monitoring.serializers import (
    CropStressEventSerializer,
    PlantingVerificationSerializer,
    PolygonObservationSerializer,
    TobaccoFieldPolygonSerializer,
)
from apps.tobacco_monitoring.services.access import polygons_visible_for_user
from apps.tobacco_monitoring.services.agromonitoring import (
    AgroMonitoringClient,
    AgroMonitoringError,
    agromonitoring_api_configured,
)
from apps.tobacco_monitoring.services.polygon_registration import register_polygon_with_provider
from apps.tobacco_monitoring.services.yield_proxy import buyer_monitoring_summary, regional_summary
from apps.tobacco_monitoring.tasks import poll_polygon_imagery_task


class TobaccoFieldPolygonListCreateView(generics.ListCreateAPIView):
    serializer_class = TobaccoFieldPolygonSerializer
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAuthenticated(), IsSmallholderFarmer()]
        return [IsAuthenticated()]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return TobaccoFieldPolygon.objects.none()
        qs = polygons_visible_for_user(self.request.user).select_related("farm")
        farm_id = self.request.query_params.get("farm")
        if farm_id:
            qs = qs.filter(farm_id=farm_id)
        return qs


class TobaccoFieldPolygonDetailView(generics.RetrieveUpdateAPIView):
    serializer_class = TobaccoFieldPolygonSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = "pk"

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return TobaccoFieldPolygon.objects.none()
        return polygons_visible_for_user(self.request.user).select_related("farm")

    def get_permissions(self):
        perms = super().get_permissions()
        if self.request.method in ("PUT", "PATCH"):
            role = getattr(self.request.user, "role", None)
            if role == UserRole.SMALLHOLDER_FARMER:
                return perms
            return [IsAuthenticated()]
        return perms


class PolygonObservationListView(generics.ListAPIView):
    serializer_class = PolygonObservationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        poly = get_object_or_404(polygons_visible_for_user(self.request.user), pk=self.kwargs["polygon_pk"])
        return PolygonObservation.objects.filter(polygon=poly).order_by("-observation_date")


class PolygonPollNowView(APIView):
    """
    Queue a single-polygon satellite poll (same pipeline as beat).

    Any user who can view the polygon may trigger this; work runs asynchronously.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, polygon_pk):
        poly = get_object_or_404(polygons_visible_for_user(request.user), pk=polygon_pk)
        had_to_register = False
        if not poly.geometry_geojson:
            return Response(
                {"detail": "Polygon has no geometry; cannot register with satellite provider."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not (poly.agromonitoring_poly_id or "").strip():
            had_to_register = True
            if not agromonitoring_api_configured():
                return Response(
                    {
                        "status": "unavailable",
                        "code": "AGROMONITORING_NOT_CONFIGURED",
                        "detail": (
                            "Satellite imagery is not enabled on this server "
                            "(AGROMONITORING_API_KEY is not set)."
                        ),
                        "queued": False,
                    },
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )
            try:
                register_polygon_with_provider(poly)
            except AgroMonitoringError as exc:
                return Response(
                    {
                        "status": "error",
                        "code": "AGROMONITORING_REGISTRATION_FAILED",
                        "detail": f"Satellite registration failed: {exc}",
                        "queued": False,
                    },
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )
            poly.refresh_from_db(
                fields=["agromonitoring_poly_id", "monitoring_status", "raw_registration_payload", "updated_at"]
            )
            if not (poly.agromonitoring_poly_id or "").strip():
                payload = poly.raw_registration_payload if isinstance(poly.raw_registration_payload, dict) else {}
                if payload.get("skipped"):
                    return Response(
                        {
                            "status": "unavailable",
                            "code": "AGROMONITORING_NOT_CONFIGURED",
                            "detail": str(payload.get("detail") or "Satellite provider is not configured."),
                            "queued": False,
                        },
                        status=status.HTTP_503_SERVICE_UNAVAILABLE,
                    )
                return Response(
                    {
                        "status": "error",
                        "code": "AGROMONITORING_NO_POLYGON_ID",
                        "detail": (
                            "Satellite provider did not return a polygon id. "
                            "Check AGROMONITORING_API_KEY and try again."
                        ),
                        "queued": False,
                    },
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )
        poll_polygon_imagery_task.delay(str(poly.id))
        return Response(
            {
                "status": "queued",
                "polygon_id": str(poly.id),
                "registered_with_provider_now": had_to_register,
            },
            status=status.HTTP_202_ACCEPTED,
        )


class PolygonLatestStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, polygon_pk):
        poly = get_object_or_404(polygons_visible_for_user(request.user), pk=polygon_pk)
        latest_ndvi = (
            poly.observations.filter(metric_type=MetricType.NDVI).order_by("-observation_date").first()
        )
        latest_moist = (
            poly.observations.filter(metric_type=MetricType.SOIL_MOISTURE)
            .order_by("-observation_date")
            .first()
        )
        ver = poly.planting_verifications.order_by("-assessed_at").first()
        return Response(
            {
                "polygon_id": str(poly.id),
                "monitoring_status": poly.monitoring_status,
                "last_imagery_check_at": poly.last_imagery_check_at,
                "last_successful_imagery_date": poly.last_successful_imagery_date,
                "latest_ndvi": PolygonObservationSerializer(latest_ndvi).data if latest_ndvi else None,
                "latest_soil_moisture": PolygonObservationSerializer(latest_moist).data if latest_moist else None,
                "planting_verification": PlantingVerificationSerializer(ver).data if ver else None,
            }
        )


class CropStressEventListView(generics.ListAPIView):
    serializer_class = CropStressEventSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = CropStressEvent.objects.filter(
            polygon_id__in=polygons_visible_for_user(self.request.user).values_list("id", flat=True)
        ).select_related("polygon")
        return qs.order_by("-created_at")


class CropStressEventDetailView(generics.RetrieveAPIView):
    serializer_class = CropStressEventSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = "pk"

    def get_queryset(self):
        return CropStressEvent.objects.filter(
            polygon_id__in=polygons_visible_for_user(self.request.user).values_list("id", flat=True)
        ).select_related("polygon")


class BuyerMonitoringSummaryView(APIView):
    permission_classes = [IsAuthenticated, IsBuyerAdminOrAuditor]

    def get(self, request):
        season = request.query_params.get("season")
        data = buyer_monitoring_summary(request.user, season=season)
        return Response(data)


class AgroMonitoringIntegrationCheckView(APIView):
    """
    Verify server-side AgroMonitoring configuration (API key + base URL).

    Does not expose the key. Any authenticated user may call; useful after
    deploying AGROMONITORING_API_KEY.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from django.conf import settings

        key = (getattr(settings, "AGROMONITORING_API_KEY", "") or "").strip()
        if not key:
            return Response(
                {
                    "configured": False,
                    "ok": False,
                    "base_url": getattr(settings, "AGROMONITORING_BASE_URL", ""),
                    "remote_polygon_count": None,
                    "detail": "AGROMONITORING_API_KEY is not set.",
                }
            )
        try:
            client = AgroMonitoringClient()
            remote = client.list_polygons()
        except AgroMonitoringError as exc:
            return Response(
                {
                    "configured": True,
                    "ok": False,
                    "base_url": getattr(settings, "AGROMONITORING_BASE_URL", ""),
                    "remote_polygon_count": None,
                    "detail": str(exc),
                },
                status=status.HTTP_200_OK,
            )
        return Response(
            {
                "configured": True,
                "ok": True,
                "base_url": getattr(settings, "AGROMONITORING_BASE_URL", ""),
                "remote_polygon_count": len(remote),
                "detail": "AgroMonitoring API accepted the key.",
            }
        )


class RegionalMonitoringSummaryView(APIView):
    """Province rollups for Zimbabwe tobacco belt."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        role = getattr(request.user, "role", None)
        if role not in (UserRole.SYSTEM_ADMIN, UserRole.REGULATOR_AUDITOR, UserRole.BUYER_CONTRACTOR):
            return Response(status=status.HTTP_403_FORBIDDEN)
        return Response(regional_summary(user=request.user))


class PlantingVerificationListCreateView(generics.ListCreateAPIView):
    serializer_class = PlantingVerificationSerializer
    permission_classes = [IsAuthenticated, IsBuyerAdminOrAuditor]

    def get_queryset(self):
        return PlantingVerificationRecord.objects.filter(
            polygon_id__in=polygons_visible_for_user(self.request.user).values_list("id", flat=True)
        ).select_related("polygon")

    def perform_create(self, serializer):
        serializer.save(assessed_by=self.request.user)
