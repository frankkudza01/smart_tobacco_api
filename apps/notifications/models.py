from django.conf import settings
from django.db import models

from apps.common.enums import NotificationType
from apps.common.models import BaseModel
from apps.organizations.models import Organization


class DeviceRegistration(BaseModel):
    """
    FCM / APNs device token for push notifications (one row per token; user may have many devices).
    org is denormalized from the user's primary org at registration time for routing; access checks
    still use the authenticated user, not client-supplied org_id.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="device_registrations",
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="device_registrations",
    )
    token = models.CharField(max_length=512, db_index=True)
    platform = models.CharField(
        max_length=16,
        choices=[("android", "android"), ("ios", "ios"), ("web", "web")],
        default="android",
    )
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        db_table = "notifications_device_registration"
        constraints = [
            models.UniqueConstraint(fields=["user", "token"], name="uniq_user_device_token"),
        ]
        indexes = [
            models.Index(fields=["user", "is_active"]),
        ]

    def __str__(self):
        return f"{self.user_id} / {self.platform}"


class Notification(BaseModel):
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    notification_type = models.CharField(
        max_length=30,
        choices=NotificationType.choices,
        default=NotificationType.INFO,
    )
    title = models.CharField(max_length=255)
    body = models.TextField(blank=True, default="")
    is_read = models.BooleanField(default=False, db_index=True)
    reference_type = models.CharField(max_length=50, blank=True, default="")
    reference_id = models.UUIDField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "notifications_notification"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["recipient", "is_read"]),
        ]

    def __str__(self):
        return f"[{self.notification_type}] {self.title} -> {self.recipient}"
