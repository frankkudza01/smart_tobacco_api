from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.org_utils import get_user_primary_organization
from apps.common.schema import EmptySchemaSerializer
from apps.notifications.models import DeviceRegistration, Notification
from apps.notifications.serializers import DeviceRegistrationSerializer, NotificationSerializer
from apps.notifications.services import mark_notifications_read


class NotificationListView(generics.ListAPIView):
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ["is_read", "notification_type"]
    ordering_fields = ["created_at"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Notification.objects.none()
        if not getattr(self.request.user, "is_authenticated", False):
            return Notification.objects.none()
        return Notification.objects.filter(recipient=self.request.user)


class MarkNotificationsReadView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = EmptySchemaSerializer

    def post(self, request):
        ids = request.data.get("notification_ids", [])
        count = mark_notifications_read(request.user, notification_ids=ids or None)
        return Response({"marked_read": count}, status=status.HTTP_200_OK)


class DeviceRegisterView(APIView):
    """Register or refresh an FCM/APNs device token for the current user."""

    permission_classes = [IsAuthenticated]
    serializer_class = DeviceRegistrationSerializer

    def post(self, request):
        ser = DeviceRegistrationSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        org = get_user_primary_organization(request.user)
        token = ser.validated_data["token"]
        platform = ser.validated_data.get("platform") or "android"
        obj, _ = DeviceRegistration.objects.update_or_create(
            user=request.user,
            token=token,
            defaults={
                "organization": org,
                "platform": platform,
                "is_active": True,
            },
        )
        return Response({"id": str(obj.id), "platform": obj.platform}, status=status.HTTP_200_OK)
