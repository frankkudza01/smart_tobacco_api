import uuid

from django.db.models import Count, Q
from django.http import Http404
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.enums import LotStatus, UserRole
from apps.farms.models import Farm
from apps.lots.models import Lot
from apps.lots.serializers import LotSerializer


def _lots_base_queryset(user):
    qs = Lot.objects.select_related("season", "farm", "farm__owner", "created_by")
    if user.role == UserRole.SMALLHOLDER_FARMER:
        return qs.filter(farm__owner=user)
    if user.role == UserRole.BUYER_CONTRACTOR:
        org_ids = user.memberships.values_list("organization_id", flat=True)
        return qs.filter(farm__organization_id__in=org_ids)
    return qs


def _assert_farm_visible_for_lots_summary(request, farm_uuid: uuid.UUID) -> None:
    farm = Farm.objects.filter(pk=farm_uuid).only("id", "owner_id", "organization_id").first()
    if farm is None:
        raise Http404()
    user = request.user
    role = getattr(user, "role", None)
    if role == UserRole.SMALLHOLDER_FARMER:
        if farm.owner_id != user.id:
            raise Http404()
    elif role == UserRole.BUYER_CONTRACTOR:
        org_ids = list(user.memberships.values_list("organization_id", flat=True))
        if not org_ids or farm.organization_id is None or farm.organization_id not in org_ids:
            raise Http404()


class LotFarmSummaryView(APIView):
    """
    Aggregated lot counts for one farm (not paginated).

    Query: ``?farm=<uuid>``

    Buckets: *graded* = ``GRADED``; *sold* = ``SOLD`` + ``SETTLED``;
    *pending* = all other statuses; *total* = all lots for the farm.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        raw_farm = (request.query_params.get("farm") or "").strip()
        if not raw_farm:
            return Response(
                {"detail": "Query parameter 'farm' is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            farm_uuid = uuid.UUID(raw_farm)
        except ValueError:
            return Response({"detail": "Invalid farm id."}, status=status.HTTP_400_BAD_REQUEST)

        _assert_farm_visible_for_lots_summary(request, farm_uuid)

        qs = _lots_base_queryset(request.user).filter(farm_id=farm_uuid)
        agg = qs.aggregate(
            total=Count("id"),
            graded=Count("id", filter=Q(status=LotStatus.GRADED)),
            sold=Count("id", filter=Q(status__in=[LotStatus.SOLD, LotStatus.SETTLED])),
            pending=Count(
                "id",
                filter=~Q(
                    status__in=[
                        LotStatus.GRADED,
                        LotStatus.SOLD,
                        LotStatus.SETTLED,
                    ]
                ),
            ),
        )

        return Response(
            {
                "farm": str(farm_uuid),
                "total": int(agg["total"] or 0),
                "pending": int(agg["pending"] or 0),
                "graded": int(agg["graded"] or 0),
                "sold": int(agg["sold"] or 0),
            }
        )


class LotListCreateView(generics.ListCreateAPIView):
    serializer_class = LotSerializer
    permission_classes = [IsAuthenticated]
    # `farm` enables farm-scoped UIs (e.g. Flutter `listLots(farmId:)` → `?farm=<uuid>`).
    filterset_fields = ["farm", "season", "status", "tobacco_type"]
    search_fields = ["lot_number", "description"]
    ordering_fields = ["created_at", "lot_number", "weight_kg"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Lot.objects.none()
        return _lots_base_queryset(self.request.user)


class LotDetailView(generics.RetrieveUpdateAPIView):
    serializer_class = LotSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = "pk"

    def get_object(self):
        qs = self.filter_queryset(self.get_queryset())
        raw = str(self.kwargs.get(self.lookup_field, "")).strip()
        try:
            lot_uuid = uuid.UUID(raw)
            return get_object_or_404(qs, pk=lot_uuid)
        except ValueError:
            return get_object_or_404(qs, lot_number__iexact=raw)

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Lot.objects.none()
        user = self.request.user
        qs = Lot.objects.select_related("season", "farm", "farm__owner")
        if user.role == UserRole.SMALLHOLDER_FARMER:
            return qs.filter(farm__owner=user)
        return qs
