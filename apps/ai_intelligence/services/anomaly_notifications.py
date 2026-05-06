"""
In-app + push notifications when a new anomaly alert is created.
Recipients are derived only from tenant-scoped relationships (farm owner, lot, etc.).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.conf import settings
from django.contrib.auth import get_user_model

from apps.common.enums import AnomalySeverity, NotificationType, UserRole
from apps.notifications.models import Notification
from apps.notifications.services import send_silent_push_to_user

if TYPE_CHECKING:
    from apps.ai_intelligence.models import AnomalyAlert

logger = logging.getLogger(__name__)


def _recipient_ids_for_alert(alert: AnomalyAlert) -> set:
    ids: set = set()

    if alert.farm_id:
        try:
            ids.add(alert.farm.owner_id)
        except Exception:
            pass
    if alert.lot_id:
        try:
            lot = alert.lot
            ids.add(lot.farm.owner_id)
        except Exception:
            pass
    if alert.document_id:
        try:
            doc = alert.document
            if doc.uploaded_by_id:
                ids.add(doc.uploaded_by_id)
            if doc.lot_id:
                ids.add(doc.lot.farm.owner_id)
        except Exception:
            pass
    if alert.settlement_id:
        try:
            if alert.settlement.farmer_id:
                ids.add(alert.settlement.farmer_id)
        except Exception:
            pass

    ids.discard(None)

    if alert.severity in (AnomalySeverity.HIGH, AnomalySeverity.CRITICAL):
        if alert.lot_id:
            from apps.organizations.models import BuyerLotAssignment
            from apps.sales.models import Sale

            for bid in BuyerLotAssignment.objects.filter(
                lot_id=alert.lot_id,
                organization_id=alert.organization_id,
            ).values_list("buyer_id", flat=True):
                if bid:
                    ids.add(bid)
            for bid in Sale.objects.filter(lot_id=alert.lot_id).values_list("buyer_id", flat=True):
                if bid:
                    ids.add(bid)

        from apps.organizations.models import OrganizationMembership

        for aid in OrganizationMembership.objects.filter(
            organization_id=alert.organization_id,
            role=UserRole.REGULATOR_AUDITOR,
            is_active=True,
        ).values_list("user_id", flat=True):
            if aid:
                ids.add(aid)

    return ids


def notify_anomaly_created(alert: AnomalyAlert) -> None:
    scheme = getattr(settings, "APP_DEEP_LINK_SCHEME", "app")
    recipient_ids = _recipient_ids_for_alert(alert)
    if not recipient_ids:
        logger.info("No recipients for anomaly alert %s", alert.id)
        return

    title = "New anomaly alert"
    body = f"Severity: {alert.severity}. Open the app to view details."
    deep = f"{scheme}://anomaly/{alert.id}"

    for uid in recipient_ids:
        Notification.objects.create(
            recipient_id=uid,
            notification_type=NotificationType.ACTION_REQUIRED,
            title=title,
            body=body,
            reference_type="anomaly_alert",
            reference_id=alert.id,
            metadata={
                "deep_link": deep,
                "anomaly_id": str(alert.id),
            },
        )
        send_silent_push_to_user(
            uid,
            {
                "type": "anomaly_alert",
                "anomaly_id": str(alert.id),
                "deep_link": deep,
            },
        )
