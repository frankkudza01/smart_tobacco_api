from rest_framework import serializers


class FarmerAdvisorTelemetrySerializer(serializers.Serializer):
    """Payload from Smart Tobacco farmer app (local prefs mirrored for analytics)."""

    event_type = serializers.CharField(max_length=32)
    week_key = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    sessions_this_week = serializers.IntegerField(required=False, min_value=0, default=0)
    advisor_queries_this_week = serializers.IntegerField(required=False, min_value=0, default=0)
    tasks_completed_this_week = serializers.IntegerField(required=False, min_value=0, default=0)
    tasks_total_this_week = serializers.IntegerField(required=False, min_value=0, default=0)
    lifetime_task_completions = serializers.IntegerField(required=False, min_value=0, default=0)
    last_usefulness_score = serializers.IntegerField(required=False, allow_null=True, min_value=1, max_value=5)
    last_sus_score = serializers.IntegerField(required=False, allow_null=True, min_value=1, max_value=5)
    task_states = serializers.ListField(
        child=serializers.DictField(child=serializers.JSONField()),
        required=False,
        default=list,
    )
