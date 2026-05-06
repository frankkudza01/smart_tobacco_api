from rest_framework import serializers


class RequestOTPSerializer(serializers.Serializer):
    phone_number = serializers.CharField(max_length=20)


class VerifyOTPSerializer(serializers.Serializer):
    phone_number = serializers.CharField(max_length=20)
    code = serializers.CharField(max_length=10, min_length=4)


class ResendOTPSerializer(serializers.Serializer):
    phone_number = serializers.CharField(max_length=20)


class OTPResponseSerializer(serializers.Serializer):
    detail = serializers.CharField()
    expires_in = serializers.IntegerField(required=False)


class OTPTokenResponseSerializer(serializers.Serializer):
    access = serializers.CharField()
    refresh = serializers.CharField()
    user_id = serializers.UUIDField()
    role = serializers.CharField()


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()
