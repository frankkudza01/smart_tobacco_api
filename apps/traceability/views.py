from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import generics, status
from rest_framework.permissions import SAFE_METHODS, BasePermission, IsAuthenticated
from rest_framework.response import Response

from apps.common.enums import UserRole
from apps.traceability.models import TraceEvent
from apps.traceability.serializers import TraceEventSerializer
from apps.traceability.services import create_trace_event


def _user_may_post_trace_for_lot(user, lot) -> bool:
    """Match TraceEventListCreateView.get_queryset write scope (buyer = org tenant, not assignment-only)."""
    if user.role == UserRole.SMALLHOLDER_FARMER:
        return lot.farm.owner_id == user.id
    if user.role == UserRole.BUYER_CONTRACTOR:
        org_ids = user.memberships.filter(is_active=True).values_list(
            "organization_id", flat=True
        )
        return lot.farm.organization_id in org_ids
    if user.role == UserRole.SYSTEM_ADMIN:
        return True
    return False


class TraceEventWritePermission(BasePermission):
    """Auditors (and similar read-only roles) may list but not POST trace events."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.method in SAFE_METHODS:
            return True
        return request.user.role != UserRole.REGULATOR_AUDITOR


class TraceEventListCreateView(generics.ListCreateAPIView):
    serializer_class = TraceEventSerializer
    permission_classes = [IsAuthenticated, TraceEventWritePermission]
    filterset_fields = ["lot", "event_type", "anchor_status"]
    ordering_fields = ["timestamp", "created_at"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return TraceEvent.objects.none()
        user = self.request.user
        qs = TraceEvent.objects.select_related("lot", "actor")
        if user.role == UserRole.SMALLHOLDER_FARMER:
            return qs.filter(lot__farm__owner=user)
        if user.role == UserRole.BUYER_CONTRACTOR:
            org_ids = user.memberships.values_list("organization_id", flat=True)
            return qs.filter(lot__farm__organization_id__in=org_ids)
        return qs

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        lot = data["lot"]
        if not _user_may_post_trace_for_lot(request.user, lot):
            return Response({"detail": "Forbidden."}, status=status.HTTP_403_FORBIDDEN)
        try:
            event = create_trace_event(
                lot=lot,
                actor=request.user,
                event_type=data["event_type"],
                timestamp=data["timestamp"],
                location=data.get("location", ""),
                latitude=data.get("latitude"),
                longitude=data.get("longitude"),
                payload=data.get("payload", {}),
                notes=data.get("notes", ""),
                prev_event_hash=data.get("prev_event_hash"),
            )
        except DjangoValidationError as exc:
            if hasattr(exc, "message_dict") and exc.message_dict:
                return Response(exc.message_dict, status=status.HTTP_400_BAD_REQUEST)
            return Response(
                {"detail": getattr(exc, "message", str(exc))},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            TraceEventSerializer(event).data,
            status=status.HTTP_201_CREATED,
        )


class TraceEventDetailView(generics.RetrieveAPIView):
    serializer_class = TraceEventSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = "pk"

    def get_queryset(self):
        return TraceEvent.objects.select_related("lot", "actor")
