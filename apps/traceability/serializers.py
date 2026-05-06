from rest_framework import serializers

from apps.common.enums import TraceEventType, UserRole
from apps.traceability.models import TraceEvent


class TraceEventSerializer(serializers.ModelSerializer):
    actor_name = serializers.CharField(source="actor.full_name", read_only=True)
    lot_number = serializers.CharField(source="lot.lot_number", read_only=True)
    prev_event_hash = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=64,
        help_text="Omit to append to chain tip; set explicitly to prove client chain state.",
    )

    class Meta:
        model = TraceEvent
        fields = [
            "id", "lot", "actor", "event_type", "timestamp",
            "location", "latitude", "longitude",
            "payload", "notes",
            "prev_event_hash",
            "event_hash",
            "anchor_status", "anchor_tx_hash",
            "actor_name", "lot_number",
            "created_at",
        ]
        read_only_fields = [
            "id", "actor", "event_hash",
            "anchor_status", "anchor_tx_hash", "created_at",
        ]

    def validate(self, attrs):
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return attrs
        user = request.user
        et = attrs.get("event_type")
        if user.role == UserRole.REGULATOR_AUDITOR:
            raise serializers.ValidationError("Auditors cannot create trace events.")
        if user.role == UserRole.SMALLHOLDER_FARMER:
            if et in (TraceEventType.GRADING, TraceEventType.SALE):
                raise serializers.ValidationError(
                    {"event_type": "Farmers cannot record GRADING or SALE events."}
                )
        elif user.role == UserRole.BUYER_CONTRACTOR:
            if et not in (TraceEventType.GRADING, TraceEventType.SALE):
                raise serializers.ValidationError(
                    {
                        "event_type": (
                            "Buyers may only record GRADING or SALE events "
                            "on lots in their organization."
                        )
                    }
                )
        return attrs

    def create(self, validated_data):
        validated_data["actor"] = self.context["request"].user
        return super().create(validated_data)
