import math
import statistics
from datetime import datetime, time

from django.db.models import Count
from django.db.models.functions import TruncDate
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_date
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics, status
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.access_control import disputes_queryset_for_org
from apps.common.org_utils import get_user_primary_organization
from apps.common.enums import DisputeStatus, UserRole
from apps.common.schema import EmptySchemaSerializer
from apps.disputes.models import Dispute, DisputeComment
from apps.disputes.serializers import (
    DisputeCommentSerializer,
    DisputeListSerializer,
    DisputeResolveSerializer,
    DisputeRespondSerializer,
    DisputeSerializer,
    DisputeLabelSerializer,
)
from apps.disputes.services.case_packet import build_dispute_case_packet


class IsBuyer(BasePermission):
    def has_permission(self, request, view):
        u = request.user
        return bool(u and u.is_authenticated and u.role == UserRole.BUYER_CONTRACTOR)


class IsAuditorOrAdmin(BasePermission):
    def has_permission(self, request, view):
        u = request.user
        return bool(u and u.is_authenticated and u.role in (UserRole.REGULATOR_AUDITOR, UserRole.SYSTEM_ADMIN))


class DisputeListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    filterset_fields = ["status", "lot", "sale", "category"]
    search_fields = ["title", "description"]
    ordering_fields = ["created_at", "status"]

    def get_serializer_class(self):
        if self.request.method == "GET":
            return DisputeListSerializer
        return DisputeSerializer

    def get_queryset(self):
        return disputes_queryset_for_org(self.request.user)


class DisputeDetailView(generics.RetrieveUpdateAPIView):
    serializer_class = DisputeSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = "pk"

    def get_queryset(self):
        return disputes_queryset_for_org(self.request.user)


class DisputeCommentNestedCreateView(generics.CreateAPIView):
    serializer_class = DisputeCommentSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return DisputeComment.objects.none()

    def perform_create(self, serializer):
        dispute = get_object_or_404(disputes_queryset_for_org(self.request.user), pk=self.kwargs["pk"])
        serializer.save(dispute=dispute, author=self.request.user)


@extend_schema(tags=["disputes"])
class DisputeRespondView(APIView):
    permission_classes = [IsAuthenticated, IsBuyer]
    serializer_class = DisputeRespondSerializer

    def post(self, request, pk):
        dispute = get_object_or_404(disputes_queryset_for_org(request.user), pk=pk)
        ser = DisputeRespondSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        DisputeComment.objects.create(
            dispute=dispute,
            author=request.user,
            body=ser.validated_data["body"][:8000],
            is_evidence=ser.validated_data.get("is_evidence", False),
        )
        if not dispute.first_response_at:
            dispute.first_response_at = timezone.now()
            dispute.save(update_fields=["first_response_at", "updated_at"])
        return Response({"status": "ok"})


@extend_schema(tags=["disputes"])
class DisputeLabelView(APIView):
    permission_classes = [IsAuthenticated, IsAuditorOrAdmin]
    serializer_class = DisputeLabelSerializer

    def post(self, request, pk):
        dispute = get_object_or_404(disputes_queryset_for_org(request.user), pk=pk)
        ser = DisputeLabelSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        dispute.status = DisputeStatus.UNDER_REVIEW
        dispute.save(update_fields=["status", "updated_at"])
        DisputeComment.objects.create(
            dispute=dispute,
            author=request.user,
            body=f"[AUDITOR_LABEL:{ser.validated_data['label']}] {ser.validated_data.get('notes', '')}"[:8000],
            is_evidence=True,
        )
        return Response({"status": "ok"})


@extend_schema(tags=["disputes"])
class DisputeResolveView(APIView):
    permission_classes = [IsAuthenticated, IsAuditorOrAdmin]
    serializer_class = DisputeResolveSerializer

    def post(self, request, pk):
        dispute = get_object_or_404(disputes_queryset_for_org(request.user), pk=pk)
        ser = DisputeResolveSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        dispute.status = ser.validated_data["status"]
        dispute.resolution = ser.validated_data.get("resolution_notes", "")[:8000]
        dispute.resolved_by = request.user
        dispute.resolved_at = timezone.now()
        dispute.save(update_fields=["status", "resolution", "resolved_by", "resolved_at", "updated_at"])
        return Response({"status": "ok"})


@extend_schema(tags=["disputes"])
class DisputeCasePacketView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = EmptySchemaSerializer

    def get(self, request, pk):
        dispute = get_object_or_404(disputes_queryset_for_org(request.user), pk=pk)
        packet = build_dispute_case_packet(user=request.user, dispute=dispute)
        if packet is None:
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
        return Response(packet)


@extend_schema(
    tags=["disputes", "analytics"],
    parameters=[
        OpenApiParameter("from", str, required=True, description="Start date (YYYY-MM-DD)"),
        OpenApiParameter("to", str, required=True, description="End date (YYYY-MM-DD)"),
    ],
    summary="Dispute lifecycle metrics for the org (auditor/admin).",
)
class DisputeAnalyticsSummaryView(APIView):
    permission_classes = [IsAuthenticated, IsAuditorOrAdmin]
    serializer_class = EmptySchemaSerializer

    def get(self, request):
        org = get_user_primary_organization(request.user)
        if org is None:
            return Response({"detail": "No organization context"}, status=status.HTTP_400_BAD_REQUEST)
        d_from = parse_date((request.query_params.get("from") or "")[:10])
        d_to = parse_date((request.query_params.get("to") or "")[:10])
        if not d_from or not d_to:
            return Response(
                {"detail": "Query params 'from' and 'to' are required (YYYY-MM-DD)."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        start = timezone.make_aware(datetime.combine(d_from, time.min))
        end = timezone.make_aware(datetime.combine(d_to, time.max))
        qs = Dispute.objects.filter(organization_id=org.id, created_at__gte=start, created_at__lte=end)
        resolution_seconds: list[float] = []
        for d in qs.filter(status=DisputeStatus.RESOLVED).exclude(resolved_at__isnull=True).iterator():
            resolution_seconds.append((d.resolved_at - d.created_at).total_seconds())
        median_sec = statistics.median(resolution_seconds) if resolution_seconds else None
        p95_sec = None
        if resolution_seconds:
            srt = sorted(resolution_seconds)
            p95_sec = srt[max(0, math.ceil(0.95 * len(srt)) - 1)]
        by_status = {row["status"]: row["c"] for row in qs.values("status").annotate(c=Count("id"))}
        volume_by_day = list(
            qs.annotate(day=TruncDate("created_at"))
            .values("day")
            .annotate(count=Count("id"))
            .order_by("day")
        )
        return Response(
            {
                "organization_id": str(org.id),
                "from": d_from.isoformat(),
                "to": d_to.isoformat(),
                "total_disputes": qs.count(),
                "by_status": by_status,
                "median_resolution_seconds": median_sec,
                "p95_resolution_seconds": p95_sec,
                "resolved_with_timing_count": len(resolution_seconds),
                "volume_by_day": volume_by_day,
            }
        )
