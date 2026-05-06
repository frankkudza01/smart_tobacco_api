from django.contrib import admin

from apps.traceability.models import TraceEvent


@admin.register(TraceEvent)
class TraceEventAdmin(admin.ModelAdmin):
    list_display = ("lot", "event_type", "actor", "timestamp", "anchor_status")
    list_filter = ("event_type", "anchor_status")
    search_fields = ("lot__lot_number", "actor__email")
    raw_id_fields = ("lot", "actor")
    readonly_fields = ("event_hash",)
