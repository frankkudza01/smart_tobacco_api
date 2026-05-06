import math

from rest_framework import serializers

from apps.common.org_utils import get_user_primary_organization
from apps.farms.geofence import (
    geolocation_geofence_consistency,
    validate_and_normalize_geofence,
)
from apps.farms.models import Farm
from apps.seasons.services import ensure_default_zimbabwe_season_for_farm


class FarmGisVerificationSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=("verify", "reject"))
    notes = serializers.CharField(required=False, allow_blank=True, default="")


class FarmLocationCheckSerializer(serializers.Serializer):
    """POST body for ``/farms/<id>/location-check/``."""

    longitude = serializers.FloatField()
    latitude = serializers.FloatField()
    horizontal_accuracy_m = serializers.IntegerField(required=False, min_value=0, max_value=5000)


class FarmSerializer(serializers.ModelSerializer):
    owner_name = serializers.CharField(source="owner.full_name", read_only=True)
    gis_verified_by_name = serializers.CharField(
        source="gis_verified_by.full_name",
        read_only=True,
        allow_null=True,
    )
    organization_id = serializers.UUIDField(write_only=True, required=False, allow_null=True)

    class Meta:
        model = Farm
        fields = [
            "id",
            "owner",
            "organization",
            "name",
            "organization_id",
            "location_description",
            "latitude",
            "longitude",
            "size_hectares",
            "district",
            "province",
            "geofence_geojson",
            "geofence_horizontal_accuracy_m",
            "boundary_check_tolerance_m",
            "is_active",
            "owner_name",
            "gis_verification_status",
            "gis_verified_at",
            "gis_verified_by",
            "gis_verified_by_name",
            "gis_verification_notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "owner",
            "gis_verification_status",
            "gis_verified_at",
            "gis_verified_by",
            "gis_verified_by_name",
            "gis_verification_notes",
            "created_at",
            "updated_at",
        ]

    def validate_geofence_geojson(self, value):
        if value in (None, {}):
            return None
        if not isinstance(value, dict):
            raise serializers.ValidationError("geofence_geojson must be an object.")
        if value.get("type") != "Polygon":
            raise serializers.ValidationError("geofence_geojson.type must be 'Polygon'.")
        coords = value.get("coordinates")
        if not isinstance(coords, list) or not coords:
            raise serializers.ValidationError("geofence_geojson.coordinates must contain at least one ring.")
        return value

    def validate_boundary_check_tolerance_m(self, value):
        if value is None:
            return value
        v = int(value)
        if v < 5 or v > 200:
            raise serializers.ValidationError("boundary_check_tolerance_m must be between 5 and 200 metres.")
        return v

    def validate(self, attrs):
        attrs = super().validate(attrs)
        geo = attrs.get("geofence_geojson")
        if geo is None or geo == {}:
            return attrs
        province = attrs.get("province")
        district = attrs.get("district")
        if self.instance is not None:
            if province is None:
                province = self.instance.province
            if district is None:
                district = self.instance.district
        try:
            attrs["geofence_geojson"] = validate_and_normalize_geofence(
                geo,
                province=str(province or ""),
                district=str(district or ""),
                clip_to_admin_region=True,
            )
        except ValueError as exc:
            raise serializers.ValidationError({"geofence_geojson": str(exc)}) from exc

        lon = attrs.get("longitude")
        lat = attrs.get("latitude")
        if self.instance is not None:
            if lon is None:
                lon = self.instance.longitude
            if lat is None:
                lat = self.instance.latitude
        tol = attrs.get("boundary_check_tolerance_m")
        if tol is None:
            tol = (
                self.instance.boundary_check_tolerance_m
                if self.instance is not None
                else Farm._meta.get_field("boundary_check_tolerance_m").default
            )
        acc = attrs.get("geofence_horizontal_accuracy_m")
        if acc is None and self.instance is not None:
            acc = self.instance.geofence_horizontal_accuracy_m

        if lon is not None and lat is not None and attrs.get("geofence_geojson"):
            chk = geolocation_geofence_consistency(
                float(lon),
                float(lat),
                attrs["geofence_geojson"],
                tolerance_m=int(tol),
                device_horizontal_accuracy_m=int(acc) if acc is not None else None,
            )
            if not chk["consistent"]:
                raise serializers.ValidationError(
                    {
                        "latitude": (
                            "GPS point is outside the farm boundary beyond the configured GPS tolerance. "
                            "Redraw the boundary, update coordinates, or increase boundary_check_tolerance_m "
                            f"(effective margin was ~{chk.get('effective_tolerance_m')} m; "
                            f"distance to edge ~{chk.get('distance_to_boundary_m')} m)."
                        )
                    }
                )
        return attrs

    def create(self, validated_data):
        request = self.context["request"]
        user = request.user
        organization_id = validated_data.pop("organization_id", None)

        if organization_id:
            membership_exists = user.memberships.filter(
                organization_id=organization_id,
                is_active=True,
            ).exists()
            if not membership_exists:
                raise serializers.ValidationError(
                    {"organization_id": "You are not an active member of this organization."}
                )
            validated_data["organization_id"] = organization_id
        else:
            org = get_user_primary_organization(user)
            if org:
                validated_data["organization"] = org

        geofence = validated_data.get("geofence_geojson")
        latitude = validated_data.get("latitude")
        longitude = validated_data.get("longitude")
        province = validated_data.get("province", "")

        if geofence is None and latitude is not None and longitude is not None:
            validated_data["geofence_geojson"] = _point_buffer_polygon(
                float(latitude),
                float(longitude),
                province=province,
                accuracy_m=validated_data.get("geofence_horizontal_accuracy_m"),
            )
            try:
                validated_data["geofence_geojson"] = validate_and_normalize_geofence(
                    validated_data["geofence_geojson"],
                    province=str(validated_data.get("province") or ""),
                    district=str(validated_data.get("district") or ""),
                    clip_to_admin_region=True,
                )
            except ValueError as exc:
                raise serializers.ValidationError({"geofence_geojson": str(exc)}) from exc

        validated_data["owner"] = user
        farm = super().create(validated_data)
        ensure_default_zimbabwe_season_for_farm(farm)
        return farm

    def update(self, instance, validated_data):
        farm = super().update(instance, validated_data)
        geo = validated_data.get("geofence_geojson")
        if geo:
            self._sync_monitoring_polygon_geometry(farm, geo)
        return farm

    @staticmethod
    def _sync_monitoring_polygon_geometry(farm, geo: dict) -> None:
        try:
            from apps.tobacco_monitoring.models import TobaccoFieldPolygon
        except Exception:
            return
        poly = (
            TobaccoFieldPolygon.objects.filter(farm=farm)
            .order_by("created_at")
            .first()
        )
        if poly is None:
            return
        poly.geometry_geojson = geo
        poly.save(update_fields=["geometry_geojson", "updated_at"])


def _point_buffer_polygon(
    latitude: float,
    longitude: float,
    province: str = "",
    *,
    accuracy_m: int | None = None,
) -> dict:
    """Square geofence around a point; expands with poor GNSS accuracy (metres)."""
    base_half_m = 125.0
    acc = float(accuracy_m) if accuracy_m is not None else 15.0
    half_m = max(base_half_m, 1.5 * max(acc, 5.0))
    dlat = half_m / 111_320.0
    dlon = half_m / (111_320.0 * max(0.2, abs(math.cos(math.radians(latitude)))))
    ring = [
        [longitude - dlon, latitude - dlat],
        [longitude + dlon, latitude - dlat],
        [longitude + dlon, latitude + dlat],
        [longitude - dlon, latitude + dlat],
        [longitude - dlon, latitude - dlat],
    ]
    return {
        "type": "Polygon",
        "coordinates": [ring],
        "province": province,
    }
