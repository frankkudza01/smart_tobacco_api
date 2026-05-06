from rest_framework import serializers

from apps.worldready.models import SusSurveyResponse, UserPreference


class UserPreferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserPreference
        fields = [
            "id",
            "preferred_language",
            "literacy_mode",
            "voice_mode_enabled",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class UserPreferenceWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserPreference
        fields = ["preferred_language", "literacy_mode", "voice_mode_enabled"]


class SusSurveySerializer(serializers.ModelSerializer):
    class Meta:
        model = SusSurveyResponse
        fields = ["scores_json", "channel"]
        extra_kwargs = {"channel": {"required": False, "default": "flutter"}}
