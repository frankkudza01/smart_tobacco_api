from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.access import can_view_farm
from apps.common.enums import FarmGisVerificationStatus, UserRole
from apps.common.permissions import IsSmallholderFarmer
from apps.farms.geofence import geolocation_geofence_consistency
from apps.farms.models import Farm
from apps.farms.serializers import (
    FarmGisVerificationSerializer,
    FarmLocationCheckSerializer,
    FarmSerializer,
)


class FarmListCreateView(generics.ListCreateAPIView):
    serializer_class = FarmSerializer

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsSmallholderFarmer()]
        return [IsAuthenticated()]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Farm.objects.none()
        user = self.request.user
        if user.role == UserRole.SMALLHOLDER_FARMER:
            return Farm.objects.filter(owner=user).select_related("owner", "organization")
        if user.role == UserRole.BUYER_CONTRACTOR:
            org_ids = user.memberships.values_list("organization_id", flat=True)
            return Farm.objects.filter(organization_id__in=org_ids).select_related("owner", "organization")
        return Farm.objects.select_related("owner", "organization").all()


class FarmDetailView(generics.RetrieveUpdateAPIView):
    serializer_class = FarmSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = "pk"

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Farm.objects.none()
        user = self.request.user
        if user.role == UserRole.SMALLHOLDER_FARMER:
            return Farm.objects.filter(owner=user)
        if user.role == UserRole.BUYER_CONTRACTOR:
            org_ids = user.memberships.values_list("organization_id", flat=True)
            return Farm.objects.filter(organization_id__in=org_ids)
        return Farm.objects.all()


class FarmGisVerificationView(APIView):
    """
    Regulator/auditor (or system admin) confirms or rejects the submitted farm boundary.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        role = getattr(request.user, "role", None)
        if role not in (UserRole.REGULATOR_AUDITOR, UserRole.SYSTEM_ADMIN):
            return Response(
                {"detail": "Only auditors or system admins can verify farm GIS."},
                status=status.HTTP_403_FORBIDDEN,
            )
        farm = get_object_or_404(Farm.objects.all(), pk=pk)
        ser = FarmGisVerificationSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        action = ser.validated_data["action"]
        notes = (ser.validated_data.get("notes") or "").strip()
        if action == "verify":
            farm.gis_verification_status = FarmGisVerificationStatus.VERIFIED
        else:
            farm.gis_verification_status = FarmGisVerificationStatus.REJECTED
        farm.gis_verified_at = timezone.now()
        farm.gis_verified_by = request.user
        farm.gis_verification_notes = notes
        farm.save(
            update_fields=[
                "gis_verification_status",
                "gis_verified_at",
                "gis_verified_by",
                "gis_verification_notes",
                "updated_at",
            ],
        )
        return Response(FarmSerializer(farm, context={"request": request}).data)


class FarmGeofenceLocationCheckView(APIView):
    """
    Check whether a GPS fix is inside the stored farm polygon, with GNSS tolerance.

    Uses ``boundary_check_tolerance_m`` plus optional device ``horizontal_accuracy_m``.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        farm = get_object_or_404(Farm.objects.select_related("owner", "organization"), pk=pk)
        user = request.user
        role = getattr(user, "role", None)
        allowed = False
        if role == UserRole.SMALLHOLDER_FARMER and farm.owner_id == user.id:
            allowed = True
        elif role in (UserRole.REGULATOR_AUDITOR, UserRole.SYSTEM_ADMIN):
            allowed = True
        elif can_view_farm(user, farm):
            allowed = True
        if not allowed:
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

        ser = FarmLocationCheckSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        geo = farm.geofence_geojson
        if not geo:
            return Response({"detail": "Farm has no geofence stored."}, status=status.HTTP_400_BAD_REQUEST)
        lon = ser.validated_data["longitude"]
        lat = ser.validated_data["latitude"]
        acc = ser.validated_data.get("horizontal_accuracy_m")
        out = geolocation_geofence_consistency(
            lon,
            lat,
            geo,
            tolerance_m=int(farm.boundary_check_tolerance_m),
            device_horizontal_accuracy_m=int(acc) if acc is not None else None,
        )
        return Response(
            {
                **out,
                "farm_id": str(farm.id),
                "boundary_check_tolerance_m": farm.boundary_check_tolerance_m,
            }
        )
