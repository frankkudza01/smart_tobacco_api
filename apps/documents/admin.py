from django.contrib import admin

from apps.documents.models import Document


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("title", "document_type", "uploaded_by", "file_size", "anchor_status", "created_at")
    list_filter = ("document_type", "anchor_status")
    search_fields = ("title", "file_name", "sha256_hash")
    raw_id_fields = ("lot", "uploaded_by")
    readonly_fields = ("sha256_hash",)
