from django.contrib import admin

from .models import FarmerAdvisorTelemetryEvent


@admin.register(FarmerAdvisorTelemetryEvent)
class FarmerAdvisorTelemetryEventAdmin(admin.ModelAdmin):
    list_display = ("created_at", "event_type", "week_key", "user", "id")
    list_filter = ("event_type", "week_key")
    search_fields = ("user__email", "user__phone_number", "week_key")
    readonly_fields = ("id", "created_at", "updated_at", "payload")
    ordering = ("-created_at",)
