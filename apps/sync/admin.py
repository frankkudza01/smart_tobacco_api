from django.contrib import admin

from apps.sync.models import SyncRecord


@admin.register(SyncRecord)
class SyncRecordAdmin(admin.ModelAdmin):
    list_display = ("idempotency_key", "payload_type", "status", "actor", "created_at")
    list_filter = ("status", "payload_type")
    search_fields = ("idempotency_key", "actor__email")
    raw_id_fields = ("actor",)
    readonly_fields = ("payload_hash",)
