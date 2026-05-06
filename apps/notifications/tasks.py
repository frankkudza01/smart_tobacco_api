import logging

from celery import shared_task

from apps.notifications.services import create_notification

logger = logging.getLogger(__name__)


@shared_task
def send_notification(recipient_id: str, notification_type: str, title: str,
                      body: str = "", reference_type: str = "", reference_id: str = None):
    from django.contrib.auth import get_user_model
    User = get_user_model()

    try:
        recipient = User.objects.get(id=recipient_id)
    except User.DoesNotExist:
        logger.error("Notification recipient %s not found", recipient_id)
        return

    create_notification(
        recipient=recipient,
        notification_type=notification_type,
        title=title,
        body=body,
        reference_type=reference_type,
        reference_id=reference_id,
    )
    logger.info("Notification sent to %s: %s", recipient.email, title)


@shared_task
def cleanup_old_notifications(days: int = 90):
    from datetime import timedelta
    from django.utils import timezone
    from apps.notifications.models import Notification

    cutoff = timezone.now() - timedelta(days=days)
    count, _ = Notification.objects.filter(created_at__lt=cutoff, is_read=True).delete()
    logger.info("Cleaned up %d old notifications", count)
