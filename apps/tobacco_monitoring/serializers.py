from __future__ import annotations

import phonenumbers
from django.conf import settings
from rest_framework import serializers

from apps.farms.models import Farm
from apps.tobacco_monitoring.models import (
    CropStressEvent,
    PlantingVerificationRecord,
    PolygonObservation,
    TobaccoFieldPolygon,
)
from apps.tobacco_monitoring.services.access import farms_visible_for_user, polygons_visible_for_user
from apps.tobacco_monitoring.services.geometry import approximate_area_hectares
from apps.tobacco_monitoring.validators import validate_geojson_polygon_payload, validate_supported_province


class TobaccoFieldPolygonSerializer(serializers.ModelSerializer):
    farm = serializers.PrimaryKeyRelatedField(queryset=Farm.objects.none())

    class Meta:
        model = TobaccoFieldPolygon
        fields = [
            "id",
            "farm",
            "field_name",
            "crop_type",
            "tobacco_class",
            "planting_date",
            "season",
            "growth_stage",
            "area_hectares",
            "province",
            "district",
            "ward",
            "monitoring_status",
            "whatsapp_phone_e164",
            "agromonitoring_poly_id",
            "last_imagery_check_at",
            "last_successful_imagery_date",
            "is_active",
            "geometry_geojson",
            "default_alert_language",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "monitoring_status",
            "agromonitoring_poly_id",
            "last_imagery_check_at",
            "last_successful_imagery_date",
            "created_at",
            "updated_at",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            self.fields["farm"].queryset = farms_visible_for_user(request.user)

    def validate_geometry_geojson(self, value):
        return validate_geojson_polygon_payload(value)

    def validate_province(self, value):
        validate_supported_province(value)
        return value

    def validate_whatsapp_phone_e164(self, value: str) -> str:
        if not value or not str(value).strip():
            return ""
        raw = value.strip()
        region = getattr(settings, "DEFAULT_COUNTRY_CODE", "ZW") or "ZW"
        try:
            num = phonenumbers.parse(raw, region)
            if not phonenumbers.is_valid_number(num):
                raise serializers.ValidationError("Invalid phone number for alerts.")
            return phonenumbers.format_number(num, phonenumbers.PhoneNumberFormat.E164)
        except phonenumbers.NumberParseException as exc:
            raise serializers.ValidationError(str(exc)) from exc

    def validate(self, attrs):
        geo = attrs.get("geometry_geojson") or (self.instance and self.instance.geometry_geojson)
        if geo and not attrs.get("area_hectares") and not (self.instance and self.instance.area_hectares):
            try:
                attrs["area_hectares"] = round(approximate_area_hectares(geo), 4)
            except Exception:
                pass
        return attrs

    def create(self, validated_data):
        request = self.context.get("request")
        if request:
            validated_data["created_by"] = request.user
        if not validated_data.get("crop_type"):
            validated_data["crop_type"] = getattr(settings, "TOBACCO_DEFAULT_CROP", "tobacco")
        poly = super().create(validated_data)

        def _enqueue():
            from apps.tobacco_monitoring.services.agromonitoring import agromonitoring_api_configured
            from apps.tobacco_monitoring.services.polygon_registration import register_polygon_with_provider
            from apps.tobacco_monitoring.tasks import register_polygon_with_agromonitoring_task

            if agromonitoring_api_configured():
                register_polygon_with_agromonitoring_task.delay(str(poly.id))
            else:
                register_polygon_with_provider(poly)

        from django.db import transaction

        transaction.on_commit(_enqueue)
        return poly


class PolygonObservationSerializer(serializers.ModelSerializer):
    class Meta:
        model = PolygonObservation
        fields = [
            "id",
            "observation_date",
            "metric_type",
            "metric_value",
            "source",
            "scene_id",
            "cloud_cover",
            "created_at",
        ]
        read_only_fields = fields


class CropStressEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = CropStressEvent
        fields = [
            "id",
            "polygon",
            "event_type",
            "severity",
            "observation_date",
            "previous_ndvi",
            "current_ndvi",
            "percentage_change",
            "growth_stage",
            "season",
            "province",
            "message_template_key",
            "localized_message",
            "status",
            "raw_reason",
            "created_at",
        ]
        read_only_fields = fields


class PlantingVerificationSerializer(serializers.ModelSerializer):
    polygon = serializers.PrimaryKeyRelatedField(queryset=TobaccoFieldPolygon.objects.none())

    class Meta:
        model = PlantingVerificationRecord
        fields = [
            "id",
            "polygon",
            "assessed_at",
            "status",
            "confidence",
            "notes",
            "assessed_by",
        ]
        read_only_fields = ["id", "assessed_at", "assessed_by"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            self.fields["polygon"].queryset = polygons_visible_for_user(request.user)

    def validate_polygon(self, poly: TobaccoFieldPolygon):
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            raise serializers.ValidationError("Authentication required.")
        if not polygons_visible_for_user(request.user).filter(pk=poly.pk).exists():
            raise serializers.ValidationError("You cannot add verification for this polygon.")
        return poly
