from django.contrib import admin
from django.contrib import messages

from apps.tobacco_monitoring.models import (
    CropStressEvent,
    PlantingVerificationRecord,
    PolygonObservation,
    SatelliteImageryRecord,
    TobaccoFieldPolygon,
    WhatsAppDeliveryLog,
)


@admin.register(TobaccoFieldPolygon)
class TobaccoFieldPolygonAdmin(admin.ModelAdmin):
    actions = ("queue_satellite_poll",)

    list_display = (
        "field_name",
        "farm",
        "province",
        "district",
        "season",
        "monitoring_status",
        "agromonitoring_poly_id",
        "is_active",
        "created_at",
    )
    list_filter = ("province", "district", "monitoring_status", "is_active", "season", "growth_stage")
    search_fields = ("field_name", "agromonitoring_poly_id", "farm__name")
    raw_id_fields = ("farm", "created_by")
    readonly_fields = ("id", "created_at", "updated_at", "raw_registration_payload")

    @admin.action(description="Queue satellite poll for selected polygons")
    def queue_satellite_poll(self, request, queryset):
        from apps.tobacco_monitoring.tasks import poll_polygon_imagery_task

        queued = 0
        for poly in queryset:
            if not poly.agromonitoring_poly_id:
                self.message_user(
                    request,
                    f"Skipped {poly.id}: no agromonitoring_poly_id.",
                    level=messages.WARNING,
                )
                continue
            poll_polygon_imagery_task.delay(str(poly.id))
            queued += 1
        self.message_user(request, f"Queued poll for {queued} polygon(s).", level=messages.SUCCESS)


@admin.register(SatelliteImageryRecord)
class SatelliteImageryRecordAdmin(admin.ModelAdmin):
    list_display = ("polygon", "acquisition_date", "source", "cloud_cover", "processed", "idempotency_key")
    list_filter = ("source", "processed")
    search_fields = ("idempotency_key", "scene_id")
    raw_id_fields = ("polygon",)


@admin.register(PolygonObservation)
class PolygonObservationAdmin(admin.ModelAdmin):
    list_display = ("polygon", "observation_date", "metric_type", "metric_value", "source")
    list_filter = ("metric_type", "source")
    raw_id_fields = ("polygon",)


@admin.register(CropStressEvent)
class CropStressEventAdmin(admin.ModelAdmin):
    list_display = ("polygon", "event_type", "severity", "observation_date", "status", "created_at")
    list_filter = ("event_type", "severity", "status", "province")
    search_fields = ("dedupe_key", "localized_message")
    raw_id_fields = ("polygon",)


@admin.register(WhatsAppDeliveryLog)
class WhatsAppDeliveryLogAdmin(admin.ModelAdmin):
    list_display = ("stress_event", "to_phone_e164", "status", "attempt_number", "created_at")
    list_filter = ("status",)
    raw_id_fields = ("stress_event",)


@admin.register(PlantingVerificationRecord)
class PlantingVerificationRecordAdmin(admin.ModelAdmin):
    list_display = ("polygon", "status", "confidence", "assessed_at", "assessed_by")
    list_filter = ("status",)
    raw_id_fields = ("polygon", "assessed_by")
