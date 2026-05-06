from rest_framework import serializers

from apps.documents.models import Document


class DocumentSerializer(serializers.ModelSerializer):
    uploaded_by_name = serializers.CharField(source="uploaded_by.full_name", read_only=True)

    class Meta:
        model = Document
        fields = [
            "id", "organization", "lot", "uploaded_by", "document_type",
            "title", "description", "file", "file_name",
            "mime_type", "file_size", "sha256_hash", "storage_pointer_hash",
            "verification_state",
            "anchor_status", "anchor_tx_hash",
            "uploaded_by_name",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "organization", "uploaded_by", "file_name", "mime_type",
            "file_size", "sha256_hash", "storage_pointer_hash", "verification_state",
            "anchor_status",
            "anchor_tx_hash", "created_at", "updated_at",
        ]


class DocumentUploadSerializer(serializers.Serializer):
    lot = serializers.UUIDField(required=False, allow_null=True)
    document_type = serializers.ChoiceField(choices=[c[0] for c in Document._meta.get_field("document_type").choices])
    title = serializers.CharField(max_length=255)
    description = serializers.CharField(required=False, default="")
    file = serializers.FileField()


class DocumentVerifyRequestSerializer(serializers.Serializer):
    doc_hash = serializers.CharField(required=False, allow_blank=True, max_length=64)
    file = serializers.FileField(required=False)


class DocumentVerificationResultSerializer(serializers.Serializer):
    document_id = serializers.UUIDField()
    stored_hash = serializers.CharField()
    recomputed_hash = serializers.CharField(allow_null=True)
    hash_match = serializers.BooleanField()
    anchor_status = serializers.CharField()
    anchor_tx_hash = serializers.CharField()
    blockchain_verified = serializers.BooleanField()
