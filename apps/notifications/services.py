import logging
from typing import Any

import requests
from django.conf import settings

from apps.notifications.models import DeviceRegistration, Notification

logger = logging.getLogger(__name__)


def send_silent_push_to_user(user_id, data: dict[str, Any]) -> None:
    """
    Optional FCM legacy HTTP data push. No-op when FCM_LEGACY_SERVER_KEY is unset.
    """
    if not getattr(settings, "FCM_LEGACY_SERVER_KEY", ""):
        logger.debug("FCM_LEGACY_SERVER_KEY not set; skip push for user=%s", user_id)
        return

    tokens = list(
        DeviceRegistration.objects.filter(user_id=user_id, is_active=True).values_list(
            "token", flat=True
        )
    )
    if not tokens:
        return

    str_data = {k: str(v) for k, v in data.items()}
    headers = {
        "Authorization": f"key={settings.FCM_LEGACY_SERVER_KEY}",
        "Content-Type": "application/json",
    }
    url = "https://fcm.googleapis.com/fcm/send"
    for token in tokens:
        body = {
            "to": token,
            "priority": "high",
            "data": str_data,
            "content_available": True,
        }
        try:
            r = requests.post(url, json=body, headers=headers, timeout=10)
            if r.status_code >= 400:
                logger.warning("FCM push failed status=%s body=%s", r.status_code, r.text[:200])
        except Exception:
            logger.exception("FCM push error user=%s", user_id)


def create_notification(*, recipient, notification_type, title, body="",
                        reference_type="", reference_id=None, metadata=None):
    return Notification.objects.create(
        recipient=recipient,
        notification_type=notification_type,
        title=title,
        body=body,
        reference_type=reference_type,
        reference_id=reference_id,
        metadata=metadata or {},
    )


def mark_notifications_read(user, notification_ids=None):
    qs = Notification.objects.filter(recipient=user, is_read=False)
    if notification_ids:
        qs = qs.filter(id__in=notification_ids)
    return qs.update(is_read=True)
