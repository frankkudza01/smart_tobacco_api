"""Minimal portable export (PII-redacted JSON) for data subject requests."""
from __future__ import annotations

from apps.ai_intelligence.models import AnomalyAlert
from apps.common.access import farms_queryset_for_user, lots_queryset_for_user
from apps.disputes.models import Dispute
from apps.documents.models import Document
from apps.privacy_controls.crypto import hash_lookup_token
from apps.ai_intelligence.services.pii_redaction import redact_structure


def build_user_export_payload(*, user, organization) -> dict:
    farms = farms_queryset_for_user(user).filter(organization=organization)
    lots = lots_queryset_for_user(user)
    docs = Document.objects.filter(lot__in=lots).values("id", "document_type", "sha256_hash", "anchor_status")[:500]
    disputes = Dispute.objects.filter(organization=organization).filter(raised_by=user)[:200]
    alerts = AnomalyAlert.objects.filter(organization=organization)[:100]
    if user.role not in ("REGULATOR_AUDITOR", "SYSTEM_ADMIN"):
        alerts = alerts.none()
    return redact_structure(
        {
            "user_id": str(user.id),
            "organization_id": str(organization.id),
            "farms": list(farms.values("id", "name", "district")),
            "lots": list(lots.values("id", "lot_number", "status")[:200]),
            "documents": list(docs),
            "disputes": list(disputes.values("id", "title", "status")),
            "alerts_count": alerts.count(),
            "phone_lookup_hash": hash_lookup_token((user.phone_number or "").strip()),
        }
    )
