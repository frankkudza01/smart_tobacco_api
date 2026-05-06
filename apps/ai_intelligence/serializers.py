from rest_framework import serializers


class ForecastQuerySerializer(serializers.Serializer):
    season_id = serializers.UUIDField(required=False, allow_null=True)
    farm_id = serializers.UUIDField(required=False, allow_null=True)
    lot_id = serializers.UUIDField(required=False, allow_null=True)
    scope = serializers.CharField(required=False, allow_blank=True, default="")


class PriceForecastQuerySerializer(serializers.Serializer):
    season_id = serializers.UUIDField(required=False, allow_null=True)
    grade = serializers.CharField(required=False, allow_blank=True, default="")
    scope = serializers.CharField(required=False, allow_blank=True, default="")


class SatelliteYieldOutlookSerializer(serializers.Serializer):
    farm_id = serializers.UUIDField()
    season_id = serializers.UUIDField(required=False, allow_null=True)


class RetrainSerializer(serializers.Serializer):
    model_type = serializers.ChoiceField(choices=["yield", "price"], default="yield")


class AnomalyRunSerializer(serializers.Serializer):
    detection_types = serializers.ListField(child=serializers.CharField(), required=False, default=list)


class ReviewLabelSerializer(serializers.Serializer):
    label = serializers.ChoiceField(choices=["confirmed", "false_positive", "needs_info"])
    notes = serializers.CharField(required=False, allow_blank=True, default="")


class AssistantChatSerializer(serializers.Serializer):
    prompt = serializers.CharField(max_length=8000)
    conversation_id = serializers.UUIDField(required=False, allow_null=True)


class AssistantGroundingSerializer(serializers.Serializer):
    """Per-response audit trail surfacing how this answer was constrained."""

    grounded = serializers.BooleanField(default=False)
    tool_count = serializers.IntegerField(default=0)
    system_prompt_version = serializers.CharField(required=False, allow_blank=True, default="")
    runtime = serializers.CharField(required=False, allow_blank=True, default="")
    hallucination_guards = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        default=list,
    )
    pii_redacted = serializers.BooleanField(default=False)
    injection_blocked = serializers.BooleanField(default=False)


class AssistantChatResponseSerializer(serializers.Serializer):
    response = serializers.CharField()
    tools_used = serializers.ListField(child=serializers.CharField(), required=False)
    blocked = serializers.BooleanField(required=False, default=False)
    conversation_id = serializers.UUIDField(required=False, allow_null=True)
    grounding = AssistantGroundingSerializer(required=False)


class EvaluationMetricSerializer(serializers.Serializer):
    metric_name = serializers.CharField(max_length=64)
    model_key = serializers.CharField(max_length=64)
    model_version = serializers.CharField(required=False, allow_blank=True, default="")
    value = serializers.DecimalField(max_digits=12, decimal_places=6, required=False, allow_null=True)
    metrics_json = serializers.JSONField(required=False, default=dict)
    notes = serializers.CharField(required=False, allow_blank=True, default="")
