from django.conf import settings
from django.db import models

from apps.common.models import BaseModel


class AuditLog(BaseModel):
    """Immutable audit log. No updates or deletes on this table."""

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="audit_logs",
    )
    action = models.CharField(max_length=100, db_index=True)
    resource_type = models.CharField(max_length=50, db_index=True)
    resource_id = models.CharField(max_length=100, blank=True, default="")
    description = models.TextField(blank=True, default="")
    changes = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=500, blank=True, default="")
    request_id = models.CharField(max_length=100, blank=True, default="", db_index=True)

    class Meta:
        db_table = "audit_audit_log"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["actor", "action"]),
            models.Index(fields=["resource_type", "resource_id"]),
        ]

    def __str__(self):
        return f"[{self.action}] {self.resource_type}:{self.resource_id} by {self.actor}"
