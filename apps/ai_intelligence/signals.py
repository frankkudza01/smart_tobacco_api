from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.ai_intelligence.models import AnomalyAlert


@receiver(post_save, sender=AnomalyAlert)
def anomaly_created_notify(sender, instance: AnomalyAlert, created: bool, **kwargs):
    if not created:
        return
    from apps.ai_intelligence.services.anomaly_notifications import notify_anomaly_created

    notify_anomaly_created(instance)
