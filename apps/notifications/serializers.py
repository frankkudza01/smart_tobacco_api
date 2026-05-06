from rest_framework import serializers

from apps.notifications.models import DeviceRegistration, Notification


class DeviceRegistrationSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeviceRegistration
        fields = ["token", "platform"]
        extra_kwargs = {
            "token": {"write_only": True},
        }


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = [
            "id", "recipient", "notification_type",
            "title", "body", "is_read",
            "reference_type", "reference_id", "metadata",
            "created_at",
        ]
        read_only_fields = ["id", "recipient", "created_at"]
