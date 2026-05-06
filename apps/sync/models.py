from django.conf import settings
from django.db import models

from apps.common.enums import SyncStatus
from apps.common.models import BaseModel


class SyncRecord(BaseModel):
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="sync_records",
    )
    client_record_id = models.UUIDField(db_index=True)
    idempotency_key = models.CharField(max_length=255, unique=True, db_index=True)
    payload_type = models.CharField(max_length=50, db_index=True)
    payload_hash = models.CharField(max_length=64, blank=True, default="")
    payload = models.JSONField(default=dict)
    status = models.CharField(
        max_length=30,
        choices=SyncStatus.choices,
        default=SyncStatus.PENDING_PROCESSING,
    )
    remote_object_id = models.UUIDField(null=True, blank=True)
    remote_object_type = models.CharField(max_length=50, blank=True, default="")
    error_detail = models.TextField(blank=True, default="")

    class Meta:
        db_table = "sync_sync_record"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["actor", "status"]),
        ]

    def __str__(self):
        return f"Sync {self.idempotency_key} ({self.status})"
