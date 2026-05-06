from django.db import connection
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.enums import UserRole
from apps.common.permissions import IsSmallholderFarmer, IsSystemAdmin
from apps.farms.models import Farm
from apps.seasons.models import FarmSeasonAssociation, Season
from apps.seasons.serializers import SeasonSerializer


def _association_table_ready() -> bool:
    # Prevent runtime 500s if code is deployed before migrations are applied.
    return FarmSeasonAssociation._meta.db_table in connection.introspection.table_names()


class SeasonListCreateView(generics.ListCreateAPIView):
    serializer_class = SeasonSerializer
    filterset_fields = ["crop_year", "status"]
    ordering_fields = ["crop_year", "created_at"]

    def get_permissions(self):
        if self.request.method == "POST":
            # Seasons are auto-generated for farms. Manual create is admin-only.
            return [IsSystemAdmin()]
        return [IsAuthenticated()]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Season.objects.none()
        if not _association_table_ready():
            return Season.objects.all()
        user = self.request.user
        qs = Season.objects.all()
        if user.role == UserRole.SMALLHOLDER_FARMER:
            return qs.filter(farm_associations__farm__owner=user).distinct()
        if user.role == UserRole.BUYER_CONTRACTOR:
            org_ids = user.memberships.values_list("organization_id", flat=True)
            return qs.filter(farm_associations__farm__organization_id__in=org_ids).distinct()
        return qs

    def get_serializer_context(self):
        context = super().get_serializer_context()
        farm_id = self.request.query_params.get("farm")
        if farm_id:
            context["farm_id"] = farm_id
        return context


class SeasonDetailView(generics.RetrieveUpdateAPIView):
    serializer_class = SeasonSerializer
    lookup_field = "pk"

    def get_permissions(self):
        # Season rows are global (one per crop year). Farmers and buyers may read;
        # only system admins may change canonical season metadata.
        if self.request.method in ("PUT", "PATCH"):
            return [IsSystemAdmin()]
        return [IsAuthenticated()]

    def get_serializer_context(self):
        context = super().get_serializer_context()
        farm_id = self.request.query_params.get("farm")
        if farm_id:
            context["farm_id"] = farm_id
        return context

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Season.objects.none()
        if not _association_table_ready():
            return Season.objects.all()
        user = self.request.user
        qs = Season.objects.all()
        if user.role == UserRole.SMALLHOLDER_FARMER:
            return qs.filter(farm_associations__farm__owner=user).distinct()
        if user.role == UserRole.BUYER_CONTRACTOR:
            org_ids = user.memberships.values_list("organization_id", flat=True)
            return qs.filter(farm_associations__farm__organization_id__in=org_ids).distinct()
        return qs


class SeasonAcceptView(APIView):
    permission_classes = [IsSmallholderFarmer]

    def patch(self, request, pk):
        if not _association_table_ready():
            return Response(
                {"detail": "Season associations are not ready. Run database migrations."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        farm_id = request.data.get("farm_id")
        if not farm_id:
            return Response({"detail": "farm_id is required."}, status=status.HTTP_400_BAD_REQUEST)

        season = Season.objects.filter(pk=pk).first()
        if not season:
            return Response({"detail": "Season not found."}, status=status.HTTP_404_NOT_FOUND)

        farm = Farm.objects.filter(pk=farm_id, owner=request.user).first()
        if not farm:
            return Response(
                {"detail": "Farm not found for current farmer."},
                status=status.HTTP_404_NOT_FOUND,
            )

        assoc, _ = FarmSeasonAssociation.objects.get_or_create(
            farm=farm,
            season=season,
        )
        if not assoc.farmer_accepted:
            assoc.farmer_accepted = True
            assoc.farmer_accepted_at = timezone.now()
            assoc.accepted_by = request.user
            assoc.save(
                update_fields=[
                    "farmer_accepted",
                    "farmer_accepted_at",
                    "accepted_by",
                    "updated_at",
                ]
            )

        serializer = SeasonSerializer(
            season,
            context={"request": request, "farm_id": str(farm_id)},
        )
        return Response(serializer.data, status=status.HTTP_200_OK)
