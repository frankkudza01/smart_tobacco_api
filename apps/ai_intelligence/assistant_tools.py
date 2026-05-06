"""
Role-scoped assistant tools. Each function MUST enforce access via apps.common.access.
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from django.utils import timezone

from apps.ai_intelligence.models import AssistantAuditLog
from apps.ai_intelligence.services.anomaly_service import AnomalyService
from apps.ai_intelligence.services.forecast_service import ForecastService
from apps.ai_intelligence.services.pii_redaction import redact_structure, redact_text
from apps.common.access import can_view_document, can_view_lot, can_view_settlement
from apps.common.enums import UserRole
from apps.disputes.models import Dispute
from apps.documents.models import Document
from apps.provenance.services import get_lot_provenance
from apps.settlements.models import Settlement

logger = logging.getLogger(__name__)


def _audit(user, tool_name: str, req: dict, resp_meta: dict) -> None:
    from apps.common.org_utils import get_user_primary_organization

    org = get_user_primary_organization(user)
    if org is None:
        return
    AssistantAuditLog.objects.create(
        organization=org,
        user=user,
        role_snapshot=user.role,
        tool_name=tool_name,
        request_meta_json=redact_structure(req),
        response_meta_json=redact_structure(resp_meta),
    )


def tool_get_my_forecasts(user) -> dict[str, Any]:
    """List yield and price forecast points visible to the current user (role-scoped)."""
    y = ForecastService.list_yield_forecasts(user)
    p = ForecastService.list_price_forecasts(user)
    meta = {"yield_n": len(y), "price_n": len(p)}
    _audit(user, "get_my_forecasts", {}, meta)
    return {"yield_forecasts": y[:40], "price_forecasts": p[:40]}


def tool_get_my_anomalies(user) -> dict[str, Any]:
    """List anomaly alerts visible to the current user."""
    data = AnomalyService.list_alerts(user)
    meta = {"count": len(data)}
    _audit(user, "get_my_anomalies", {}, meta)
    return {"anomalies": data[:50]}


def tool_explain_my_alert(user, alert_id: str) -> dict[str, Any]:
    """Summarize a single alert the user is allowed to see (PII-redacted, optional LLM)."""
    from django.conf import settings

    try:
        aid = UUID(alert_id)
    except ValueError:
        return {"error": "invalid_alert_id"}
    packet = AnomalyService.case_packet(user, aid)
    if not packet:
        return {"error": "not_found_or_forbidden"}
    summary_src = redact_text(str(packet.get("alert", {})))
    if not settings.AI_ENABLED or not settings.OPENAI_API_KEY:
        _audit(user, "explain_my_alert", {"alert_id": alert_id}, {"fallback": True})
        return {"explanation": "Alert details retrieved. Enable AI for natural-language explanation."}
    from apps.ai_intelligence.services.openai_safe import chat_simple

    sys_p = (
        "You summarize anomaly alerts for the requesting user only. "
        "Do not invent data. Use only the provided redacted summary."
    )
    try:
        expl = chat_simple(
            system_prompt=sys_p,
            user_message=f"Summarize this alert for the user in 3 short bullet points:\n{summary_src}",
        )
    except Exception as exc:
        logger.warning("explain_my_alert LLM failed: %s", exc)
        expl = "Could not generate explanation at this time."
    _audit(user, "explain_my_alert", {"alert_id": alert_id}, {"ok": True})
    return {"explanation": expl}


def tool_create_dispute(user, lot_id: str, title: str, description: str) -> dict[str, Any]:
    """Farmers only: open a dispute on a lot they own (access-checked)."""
    if user.role != UserRole.SMALLHOLDER_FARMER:
        return {"error": "forbidden"}
    try:
        lid = UUID(lot_id)
    except ValueError:
        return {"error": "invalid_lot_id"}
    from apps.lots.models import Lot

    try:
        lot = Lot.objects.select_related("season", "farm").get(id=lid)
    except Lot.DoesNotExist:
        return {"error": "lot_not_found"}
    if not can_view_lot(user, lot):
        return {"error": "forbidden"}
    d = Dispute.objects.create(
        lot=lot,
        raised_by=user,
        title=redact_text(title)[:255],
        description=redact_text(description)[:4000],
    )
    _audit(user, "create_dispute", {"lot_id": lot_id}, {"dispute_id": str(d.id)})
    return {"dispute_id": str(d.id), "status": d.status}


def tool_get_portfolio_forecasts(user) -> dict[str, Any]:
    """Buyers: forecasts for assigned / purchased lots only."""
    if user.role != UserRole.BUYER_CONTRACTOR:
        return {"error": "forbidden"}
    y = ForecastService.list_yield_forecasts(user)
    p = ForecastService.list_price_forecasts(user)
    _audit(user, "get_portfolio_forecasts", {}, {"yield_n": len(y), "price_n": len(p)})
    return {"yield_forecasts": y[:40], "price_forecasts": p[:40]}


def tool_get_portfolio_anomalies(user) -> dict[str, Any]:
    """Buyers: anomalies tied to their portfolio scope."""
    if user.role != UserRole.BUYER_CONTRACTOR:
        return {"error": "forbidden"}
    data = AnomalyService.list_alerts(user)
    _audit(user, "get_portfolio_anomalies", {}, {"count": len(data)})
    return {"anomalies": data[:50]}


def tool_open_case_packet(user, alert_id: str) -> dict[str, Any]:
    try:
        aid = UUID(alert_id)
    except ValueError:
        return {"error": "invalid_alert_id"}
    packet = AnomalyService.case_packet(user, aid)
    if not packet:
        return {"error": "not_found_or_forbidden"}
    _audit(user, "open_case_packet", {"alert_id": alert_id}, {"evidence_n": len(packet.get("evidence", []))})
    return packet


def tool_hold_settlement(user, settlement_id: str) -> dict[str, Any]:
    """Buyers: mark a settlement DISPUTED if it is in their scope (review hold)."""
    if user.role != UserRole.BUYER_CONTRACTOR:
        return {"error": "forbidden"}
    try:
        sid = UUID(settlement_id)
    except ValueError:
        return {"error": "invalid_settlement_id"}
    try:
        s = Settlement.objects.select_related("sale", "sale__lot", "sale__lot__farm").get(id=sid)
    except Settlement.DoesNotExist:
        return {"error": "not_found"}
    if not can_view_settlement(user, s):
        return {"error": "forbidden"}
    from apps.common.enums import SettlementStatus

    s.status = SettlementStatus.DISPUTED
    s.notes = (s.notes or "") + f"\n[Hold via assistant {timezone.now().isoformat()}]"
    s.save(update_fields=["status", "notes", "updated_at"])
    _audit(user, "hold_settlement", {"settlement_id": settlement_id}, {"status": s.status})
    return {"settlement_id": str(s.id), "status": s.status}


def tool_search_anomalies(user, status: str | None = None) -> dict[str, Any]:
    """Auditors/admins: search anomalies within the organization."""
    if user.role not in (UserRole.REGULATOR_AUDITOR, UserRole.SYSTEM_ADMIN):
        return {"error": "forbidden"}
    data = AnomalyService.list_alerts(user, status=status)
    _audit(user, "search_anomalies", {"status": status}, {"count": len(data)})
    return {"anomalies": data[:100]}


def tool_export_case_packet(user, alert_id: str) -> dict[str, Any]:
    """Auditors/admins: export case packet JSON for an alert."""
    if user.role not in (UserRole.REGULATOR_AUDITOR, UserRole.SYSTEM_ADMIN):
        return {"error": "forbidden"}
    return tool_open_case_packet(user, alert_id)


def tool_verify_document_hash(user, document_id: str) -> dict[str, Any]:
    """Return document hash and anchor status only (no file content)."""
    try:
        did = UUID(document_id)
    except ValueError:
        return {"error": "invalid_document_id"}
    try:
        doc = Document.objects.select_related("lot").get(id=did)
    except Document.DoesNotExist:
        return {"error": "not_found"}
    if not can_view_document(user, doc):
        return {"error": "forbidden"}
    _audit(user, "verify_document_hash", {"document_id": document_id}, {"has_hash": bool(doc.sha256_hash)})
    return {
        "document_id": str(doc.id),
        "sha256_hash": doc.sha256_hash,
        "anchor_status": doc.anchor_status,
    }


def tool_audit_provenance_timeline(user, lot_id: str) -> dict[str, Any]:
    """Auditors/admins: provenance timeline for a lot (PII-redacted)."""
    try:
        lid = UUID(lot_id)
    except ValueError:
        return {"error": "invalid_lot_id"}
    from apps.lots.models import Lot

    try:
        lot = Lot.objects.select_related("season", "farm").get(id=lid)
    except Lot.DoesNotExist:
        return {"error": "not_found"}
    if not can_view_lot(user, lot):
        return {"error": "forbidden"}
    prov = get_lot_provenance(str(lot.id), queried_by=user)
    if prov is None:
        return {"error": "not_found"}
    redacted = redact_structure(prov)
    _audit(user, "audit_provenance_timeline", {"lot_id": lot_id}, {"sections": list(redacted.keys())})
    return redacted


FARMER_TOOLS = {
    "get_my_forecasts": tool_get_my_forecasts,
    "get_my_anomalies": tool_get_my_anomalies,
    "explain_my_alert": tool_explain_my_alert,
    "create_dispute": tool_create_dispute,
}

BUYER_TOOLS = {
    "get_portfolio_forecasts": tool_get_portfolio_forecasts,
    "get_portfolio_anomalies": tool_get_portfolio_anomalies,
    "open_case_packet": tool_open_case_packet,
    "hold_settlement": tool_hold_settlement,
}

AUDITOR_TOOLS = {
    "search_anomalies": tool_search_anomalies,
    "export_case_packet": tool_export_case_packet,
    "verify_document_hash": tool_verify_document_hash,
    "audit_provenance_timeline": tool_audit_provenance_timeline,
}


def tools_for_user(user):
    """Build LangChain tools with `user` bound (LLM supplies remaining parameters only)."""
    from functools import partial

    from langchain_core.tools import StructuredTool

    registry: dict[str, callable] = {}
    if user.role == UserRole.SMALLHOLDER_FARMER:
        registry.update(FARMER_TOOLS)
    elif user.role == UserRole.BUYER_CONTRACTOR:
        registry.update(BUYER_TOOLS)
    elif user.role == UserRole.REGULATOR_AUDITOR:
        registry.update(AUDITOR_TOOLS)
    elif user.role == UserRole.SYSTEM_ADMIN:
        registry = {**FARMER_TOOLS, **BUYER_TOOLS, **AUDITOR_TOOLS}

    lc_tools = []
    for name, fn in registry.items():
        bound = partial(fn, user)
        bound.__name__ = name  # type: ignore[attr-defined]
        lc_tools.append(
            StructuredTool.from_function(
                func=bound,
                name=name,
                description=(fn.__doc__ or name).strip(),
            )
        )
    return lc_tools
