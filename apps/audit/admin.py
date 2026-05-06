from django.contrib import admin

from apps.audit.models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("action", "resource_type", "resource_id", "actor", "request_id", "created_at")
    list_filter = ("action", "resource_type")
    search_fields = ("actor__email", "resource_id", "request_id", "description")
    raw_id_fields = ("actor",)
    readonly_fields = (
        "actor", "action", "resource_type", "resource_id",
        "description", "changes", "ip_address", "user_agent", "request_id",
    )

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
