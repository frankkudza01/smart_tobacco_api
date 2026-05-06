from django.conf import settings
from django.db import models

from apps.common.enums import BlockchainAnchorStatus, DocumentType, DocumentVerificationState
from apps.common.models import BaseModel
from apps.lots.models import Lot
from apps.organizations.models import Organization


def document_upload_path(instance, filename):
    return f"documents/{instance.uploaded_by_id}/{filename}"


class Document(BaseModel):
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="documents",
        null=True,
        blank=True,
        db_index=True,
    )
    lot = models.ForeignKey(
        Lot,
        on_delete=models.CASCADE,
        related_name="documents",
        null=True,
        blank=True,
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="documents",
    )
    document_type = models.CharField(max_length=30, choices=DocumentType.choices, db_index=True)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    file = models.FileField(upload_to=document_upload_path)
    file_name = models.CharField(max_length=255, blank=True, default="")
    mime_type = models.CharField(max_length=100, blank=True, default="")
    file_size = models.PositiveIntegerField(default=0)
    sha256_hash = models.CharField(max_length=64, db_index=True, blank=True, default="")
    storage_pointer_hash = models.CharField(max_length=64, blank=True, default="", db_index=True)
    verification_state = models.CharField(
        max_length=20,
        choices=DocumentVerificationState.choices,
        default=DocumentVerificationState.UPLOADED,
        db_index=True,
    )
    anchor_status = models.CharField(
        max_length=20,
        choices=BlockchainAnchorStatus.choices,
        default=BlockchainAnchorStatus.PENDING,
    )
    anchor_tx_hash = models.CharField(max_length=66, blank=True, default="")

    class Meta:
        db_table = "documents_document"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["document_type", "created_at"]),
        ]

    def __str__(self):
        return f"{self.title} ({self.document_type})"


class DocumentFingerprint(BaseModel):
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="document_fingerprints",
        db_index=True,
    )
    document = models.OneToOneField(
        Document,
        on_delete=models.CASCADE,
        related_name="fingerprint",
    )
    extracted_text_redacted = models.TextField(blank=True, default="")
    embedding_json = models.JSONField(default=list, blank=True)
    key_fields_json = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "documents_document_fingerprint"
        indexes = [
            models.Index(fields=["organization", "document"]),
        ]
