from django.contrib import admin

from apps.notifications.models import DeviceRegistration, Notification


@admin.register(DeviceRegistration)
class DeviceRegistrationAdmin(admin.ModelAdmin):
    list_display = ("user", "platform", "is_active", "organization", "created_at")
    list_filter = ("platform", "is_active")
    raw_id_fields = ("user", "organization")


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("title", "recipient", "notification_type", "is_read", "created_at")
    list_filter = ("notification_type", "is_read")
    search_fields = ("title", "recipient__email")
    raw_id_fields = ("recipient",)
