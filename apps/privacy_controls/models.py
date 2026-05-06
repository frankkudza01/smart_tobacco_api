from __future__ import annotations

from django.conf import settings
from django.db import models

from apps.common.models import BaseModel
from apps.organizations.models import Organization


class DataSubjectRequestType(models.TextChoices):
    EXPORT = "export", "Export my data"
    DELETE = "delete", "Request erasure"


class DataSubjectRequestStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    PROCESSING = "processing", "Processing"
    COMPLETED = "completed", "Completed"
    REJECTED = "rejected", "Rejected"


class DataSubjectRequest(BaseModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="privacy_requests",
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="privacy_requests",
        db_index=True,
    )
    request_type = models.CharField(max_length=16, choices=DataSubjectRequestType.choices)
    status = models.CharField(
        max_length=16,
        choices=DataSubjectRequestStatus.choices,
        default=DataSubjectRequestStatus.PENDING,
        db_index=True,
    )
    notes = models.TextField(blank=True, default="")

    class Meta:
        db_table = "privacy_controls_data_subject_request"
        ordering = ["-created_at"]
