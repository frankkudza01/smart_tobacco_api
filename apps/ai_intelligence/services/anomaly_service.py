from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from apps.ai_intelligence.models import AnomalyAlert, AnomalyEvidence, ReviewLabel
from apps.common.access import can_view_anomaly_alert
from apps.common.enums import AnomalyAlertStatus, ReviewLabelChoice
from apps.common.org_utils import get_user_primary_organization

logger = logging.getLogger(__name__)


class AnomalyService:
    @staticmethod
    def alerts_for_user(user):
        org = get_user_primary_organization(user)
        if org is None:
            return AnomalyAlert.objects.none()
        qs = AnomalyAlert.objects.filter(organization=org).select_related(
            "lot", "farm", "document", "settlement"
        )
        if user.role == "SMALLHOLDER_FARMER":
            from apps.common.access import farms_queryset_for_user, lots_queryset_for_user

            farm_ids = farms_queryset_for_user(user).values_list("id", flat=True)
            lot_ids = lots_queryset_for_user(user).values_list("id", flat=True)
            from django.db.models import Q

            return qs.filter(
                Q(farm_id__in=farm_ids)
                | Q(lot_id__in=lot_ids)
                | Q(document__lot_id__in=lot_ids)
                | Q(settlement__sale__lot_id__in=lot_ids)
            ).distinct()
        if user.role == "BUYER_CONTRACTOR":
            from apps.common.access import lots_queryset_for_user
            from django.db.models import Q

            lot_ids = lots_queryset_for_user(user).values_list("id", flat=True)
            return qs.filter(
                Q(lot_id__in=lot_ids)
                | Q(document__lot_id__in=lot_ids)
                | Q(settlement__sale__lot_id__in=lot_ids)
            ).distinct()
        if user.role in ("REGULATOR_AUDITOR", "SYSTEM_ADMIN"):
            return qs
        return AnomalyAlert.objects.none()

    @staticmethod
    def list_alerts(
        user,
        *,
        status: str | None = None,
        severity: str | None = None,
        alert_type: str | None = None,
        subject: str | None = None,
    ) -> list[dict[str, Any]]:
        qs = AnomalyService.alerts_for_user(user)
        if status:
            qs = qs.filter(status=status)
        if severity:
            qs = qs.filter(severity=severity)
        if alert_type:
            qs = qs.filter(alert_type=alert_type)
        if subject == "lot":
            qs = qs.filter(lot_id__isnull=False)
        elif subject == "document":
            qs = qs.filter(document_id__isnull=False)
        rows = qs.order_by("-detected_at")[:200]
        return [AnomalyService._serialize_alert(a, user) for a in rows]

    @staticmethod
    def _serialize_alert(a: AnomalyAlert, user) -> dict[str, Any]:
        out = {
            "id": str(a.id),
            "alert_type": a.alert_type,
            "severity": a.severity,
            "score": str(a.score),
            "status": a.status,
            "detected_at": a.detected_at.isoformat(),
            "model_version": a.model_version,
            "title": a.title,
            "lot_id": str(a.lot_id) if a.lot_id else None,
            "farm_id": str(a.farm_id) if a.farm_id else None,
            "document_id": str(a.document_id) if a.document_id else None,
            "settlement_id": str(a.settlement_id) if a.settlement_id else None,
        }
        if user.role in ("REGULATOR_AUDITOR", "SYSTEM_ADMIN"):
            out["evidence_count"] = a.evidence_items.count()
        return out

    @staticmethod
    def get_alert(user, alert_id: UUID) -> AnomalyAlert | None:
        try:
            alert = AnomalyAlert.objects.select_related("organization").get(id=alert_id)
        except AnomalyAlert.DoesNotExist:
            return None
        if not can_view_anomaly_alert(user, alert):
            return None
        return alert

    @staticmethod
    def case_packet(user, alert_id: UUID) -> dict[str, Any] | None:
        alert = AnomalyService.get_alert(user, alert_id)
        if alert is None:
            return None
        evidence = list(
            alert.evidence_items.values("id", "evidence_type", "payload_json", "created_at")
        )
        # Redact evidence payloads for farmer/buyer — keep structure, redact string values
        from apps.ai_intelligence.services.pii_redaction import redact_structure

        if user.role == "SMALLHOLDER_FARMER":
            evidence = redact_structure(evidence)
        elif user.role == "BUYER_CONTRACTOR":
            evidence = redact_structure(evidence)
        return {
            "alert": AnomalyService._serialize_alert(alert, user),
            "evidence": evidence,
            "exported_at": timezone.now().isoformat(),
        }

    @staticmethod
    @transaction.atomic
    def add_review_label(*, user, alert_id: UUID, label: str, notes: str = "") -> ReviewLabel | None:
        alert = AnomalyService.get_alert(user, alert_id)
        if alert is None:
            return None
        if user.role not in ("REGULATOR_AUDITOR", "SYSTEM_ADMIN"):
            return None
        rl = ReviewLabel.objects.create(
            organization=alert.organization,
            alert=alert,
            label=label,
            reviewer=user,
            notes=notes[:4000],
        )
        if label == ReviewLabelChoice.FALSE_POSITIVE:
            alert.status = AnomalyAlertStatus.CLOSED
        elif label == ReviewLabelChoice.CONFIRMED:
            alert.status = AnomalyAlertStatus.REVIEWING
        else:
            alert.status = AnomalyAlertStatus.REVIEWING
        alert.save(update_fields=["status", "updated_at"])
        return rl
