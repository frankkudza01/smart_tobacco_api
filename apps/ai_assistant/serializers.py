from rest_framework import serializers


class AIQuerySerializer(serializers.Serializer):
    prompt = serializers.CharField(max_length=2000)
    context = serializers.JSONField(required=False, default=dict)


class AIResponseSerializer(serializers.Serializer):
    response = serializers.CharField()
    tools_used = serializers.ListField(child=serializers.CharField(), required=False, default=list)
    blocked = serializers.BooleanField(required=False, default=False)
