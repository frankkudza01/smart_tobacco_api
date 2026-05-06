from rest_framework import serializers

from apps.common.enums import DisputeCategory, DisputeStatus, UserRole
from apps.disputes.models import Dispute, DisputeComment


class DisputeCommentSerializer(serializers.ModelSerializer):
    author_name = serializers.CharField(source="author.full_name", read_only=True)

    class Meta:
        model = DisputeComment
        fields = [
            "id", "dispute", "author", "body",
            "is_evidence", "attachment",
            "author_name", "created_at",
        ]
        read_only_fields = ["id", "author", "created_at"]

    def create(self, validated_data):
        if "author" not in validated_data:
            validated_data["author"] = self.context["request"].user
        return super().create(validated_data)


class DisputeSerializer(serializers.ModelSerializer):
    raised_by_name = serializers.CharField(source="raised_by.full_name", read_only=True)
    comments = DisputeCommentSerializer(many=True, read_only=True)
    comment_count = serializers.IntegerField(source="comments.count", read_only=True)

    class Meta:
        model = Dispute
        fields = [
            "id", "organization", "lot", "sale", "raised_by", "assigned_to",
            "title", "description", "category",
            "related_trace_event_ids", "related_document_ids", "related_anomaly_ids",
            "opened_by_role", "first_response_at", "resolved_by",
            "status",
            "resolution", "resolved_at",
            "raised_by_name", "comments", "comment_count",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "raised_by", "resolved_at", "organization",
            "opened_by_role", "first_response_at", "resolved_by",
            "created_at", "updated_at",
        ]

    def create(self, validated_data):
        user = self.context["request"].user
        validated_data["raised_by"] = user
        validated_data["opened_by_role"] = user.role
        lot = validated_data.get("lot")
        sale = validated_data.get("sale")
        org_id = None
        if lot is not None:
            org_id = lot.farm.organization_id
        elif sale is not None:
            org_id = sale.lot.farm.organization_id
        validated_data["organization_id"] = org_id
        return super().create(validated_data)


class DisputeListSerializer(serializers.ModelSerializer):
    raised_by_name = serializers.CharField(source="raised_by.full_name", read_only=True)
    comment_count = serializers.IntegerField(source="comments.count", read_only=True)

    class Meta:
        model = Dispute
        fields = [
            "id", "lot", "sale", "raised_by",
            "title", "status", "category",
            "raised_by_name",
            "comment_count", "created_at",
        ]


class DisputeRespondSerializer(serializers.Serializer):
    body = serializers.CharField(max_length=8000)
    is_evidence = serializers.BooleanField(required=False, default=False)


class DisputeLabelSerializer(serializers.Serializer):
    label = serializers.ChoiceField(choices=["confirmed", "false_positive", "needs_info"])
    notes = serializers.CharField(required=False, allow_blank=True, default="")


class DisputeResolveSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=[DisputeStatus.RESOLVED, DisputeStatus.REJECTED])
    resolution_notes = serializers.CharField(required=False, allow_blank=True, default="")
