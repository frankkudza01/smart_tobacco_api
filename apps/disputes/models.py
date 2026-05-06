from django.conf import settings
from django.db import models

from apps.common.enums import DisputeCategory, DisputeStatus
from apps.common.models import BaseModel
from apps.lots.models import Lot
from apps.organizations.models import Organization
from apps.sales.models import Sale


class Dispute(BaseModel):
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="disputes",
        null=True,
        blank=True,
        db_index=True,
    )
    lot = models.ForeignKey(Lot, on_delete=models.CASCADE, related_name="disputes", null=True, blank=True)
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name="disputes", null=True, blank=True)
    raised_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="disputes_raised",
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="disputes_assigned",
    )
    title = models.CharField(max_length=255)
    description = models.TextField()
    category = models.CharField(
        max_length=32,
        choices=DisputeCategory.choices,
        blank=True,
        default="",
        db_index=True,
    )
    related_trace_event_ids = models.JSONField(default=list, blank=True)
    related_document_ids = models.JSONField(default=list, blank=True)
    related_anomaly_ids = models.JSONField(default=list, blank=True)
    opened_by_role = models.CharField(max_length=32, blank=True, default="", db_index=True)
    first_response_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="disputes_resolved",
    )
    status = models.CharField(
        max_length=20,
        choices=DisputeStatus.choices,
        default=DisputeStatus.OPEN,
        db_index=True,
    )
    resolution = models.TextField(blank=True, default="")
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "disputes_dispute"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Dispute: {self.title} ({self.status})"


class DisputeComment(BaseModel):
    dispute = models.ForeignKey(Dispute, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="dispute_comments",
    )
    body = models.TextField()
    is_evidence = models.BooleanField(default=False)
    attachment = models.FileField(upload_to="dispute_evidence/", blank=True, null=True)

    class Meta:
        db_table = "disputes_dispute_comment"
        ordering = ["created_at"]

    def __str__(self):
        return f"Comment on {self.dispute.title} by {self.author}"
