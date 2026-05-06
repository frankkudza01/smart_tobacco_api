from django.urls import path

from apps.notifications.views import MarkNotificationsReadView, NotificationListView

urlpatterns = [
    path("", NotificationListView.as_view(), name="notification-list"),
    path("mark-read/", MarkNotificationsReadView.as_view(), name="notification-mark-read"),
]
