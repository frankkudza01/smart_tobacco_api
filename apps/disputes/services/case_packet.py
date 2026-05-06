"""Governance-grade dispute case packet (JSON) — role-scoped, PII-redacted."""
from __future__ import annotations

from apps.ai_intelligence.models import AnomalyAlert
from apps.ai_intelligence.services.anomaly_service import AnomalyService
from apps.ai_intelligence.services.pii_redaction import redact_structure
from apps.common.access import can_view_dispute
from apps.documents.models import Document
from apps.documents.services import verify_document
from apps.disputes.models import Dispute
from apps.grading.models import GradeRecord
from apps.provenance.services import get_lot_provenance
from apps.sales.models import Sale


def build_dispute_case_packet(*, user, dispute: Dispute) -> dict | None:
    if not can_view_dispute(user, dispute):
        return None
    lot = dispute.lot
    prov = None
    if lot:
        prov = get_lot_provenance(str(lot.id), queried_by=user)
    docs = []
    if lot:
        for doc in Document.objects.filter(lot=lot)[:50]:
            vr = verify_document(doc)
            docs.append(
                {
                    "document_id": str(doc.id),
                    "verification_state": doc.verification_state,
                    "hash_match": vr.get("hash_match"),
                    "anchor_status": doc.anchor_status,
                }
            )
    near_dup = []
    if dispute.organization_id:
        for aid in dispute.related_anomaly_ids or []:
            try:
                al = AnomalyAlert.objects.get(id=aid, organization_id=dispute.organization_id)
            except AnomalyAlert.DoesNotExist:
                continue
            pkt = AnomalyService.case_packet(user, al.id)
            if pkt:
                near_dup.append(pkt)
    grades = []
    sales = []
    if lot:
        grades = list(GradeRecord.objects.filter(lot=lot).values("grade", "weight_kg", "graded_at", "graded_by_id"))
        sales = list(Sale.objects.filter(lot=lot).values("total_amount", "price_per_kg", "sale_date", "buyer_id"))
    timeline_authors = []
    if prov and isinstance(prov.get("timeline"), list):
        for ev in prov["timeline"][:100]:
            timeline_authors.append(
                {
                    "event_type": ev.get("event_type"),
                    "timestamp": str(ev.get("timestamp")),
                    "actor_hint": "[REDACTED]",
                }
            )
    out = {
        "dispute_id": str(dispute.id),
        "status": dispute.status,
        "category": dispute.category or None,
        "title": dispute.title,
        "description_excerpt": dispute.description[:500] if dispute.description else "",
        "opened_by_id": str(dispute.raised_by_id) if dispute.raised_by_id else None,
        "opened_by_role": dispute.opened_by_role or None,
        "provenance_summary": {"lot_id": str(lot.id), "lot_number": lot.lot_number} if lot else None,
        "timeline_authorship": timeline_authors,
        "document_verification": docs,
        "near_duplicate_cases": near_dup,
        "grading_records": grades,
        "sales_records": sales,
        "related_trace_event_ids": dispute.related_trace_event_ids,
        "related_document_ids": dispute.related_document_ids,
        "related_anomaly_ids": dispute.related_anomaly_ids,
        "resolution": dispute.resolution[:2000] if dispute.resolution else "",
        "resolved_by_id": str(dispute.resolved_by_id) if dispute.resolved_by_id else None,
    }
    return redact_structure(out)
