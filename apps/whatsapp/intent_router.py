"""
Intent routing engine for WhatsApp messages.

Two-phase routing:
1. Deterministic keyword matching for known commands.
2. LangChain AI fallback for free-text understanding.

Intents are role-aware — farmers and buyers get different command sets.
"""
import logging
import re

from apps.common.enums import ConversationType, UserRole
from apps.whatsapp.models import WhatsAppContact, WhatsAppConversation, WhatsAppIntentLog
from apps.whatsapp.session_service import (
    advance_state,
    end_conversation,
    get_active_conversation,
    start_conversation,
)

logger = logging.getLogger(__name__)


FARMER_INTENTS = {
    "register": ConversationType.ONBOARDING,
    "activate": ConversationType.ONBOARDING,
    "register farm": ConversationType.FARM_REGISTRATION,
    "create farm": ConversationType.FARM_REGISTRATION,
    "new farm": ConversationType.FARM_REGISTRATION,
    "create season": ConversationType.SEASON_CREATION,
    "new season": ConversationType.SEASON_CREATION,
    "create lot": ConversationType.LOT_CREATION,
    "new lot": ConversationType.LOT_CREATION,
    "add event": ConversationType.EVENT_CAPTURE,
    "record event": ConversationType.EVENT_CAPTURE,
    "capture event": ConversationType.EVENT_CAPTURE,
    "upload document": ConversationType.DOCUMENT_UPLOAD,
    "upload receipt": ConversationType.DOCUMENT_UPLOAD,
    "upload certificate": ConversationType.DOCUMENT_UPLOAD,
    "upload evidence": ConversationType.DOCUMENT_UPLOAD,
    "raise dispute": ConversationType.DISPUTE_CREATION,
    "new dispute": ConversationType.DISPUTE_CREATION,
    "dispute": ConversationType.DISPUTE_CREATION,
}

BUYER_INTENTS = {
    "record grading": ConversationType.GRADING,
    "grade lot": ConversationType.GRADING,
    "grading": ConversationType.GRADING,
    "record sale": ConversationType.SALE_RECORDING,
    "new sale": ConversationType.SALE_RECORDING,
    "create settlement": ConversationType.SETTLEMENT,
    "update settlement": ConversationType.SETTLEMENT,
    "update payment": ConversationType.SETTLEMENT,
    "respond dispute": ConversationType.DISPUTE_RESPONSE,
    "dispute response": ConversationType.DISPUTE_RESPONSE,
    "upload grading sheet": ConversationType.DOCUMENT_UPLOAD,
    "upload transaction document": ConversationType.DOCUMENT_UPLOAD,
}

LOOKUP_PATTERNS = [
    (r"^my settlements?$", "lookup_settlements"),
    (r"^my payment$", "lookup_settlements"),
    (r"^settlements?$", "lookup_settlements"),
    (r"^where is my payment", "lookup_settlements"),
    (r"^trace lot\s+(.+)", "lookup_trace_lot"),
    (r"^status of lot\s+(.+)", "lookup_trace_lot"),
    (r"^lot status\s+(.+)", "lookup_trace_lot"),
    (r"^verify document\s+(.+)", "lookup_verify_document"),
    (r"^verify my document\s+(.+)", "lookup_verify_document"),
    (r"^dispute status\s*(.+)?$", "lookup_dispute_status"),
    (r"^my documents?$", "lookup_my_documents"),
    (r"^view lots?$", "lookup_my_lots"),
    (r"^my lots?$", "lookup_my_lots"),
    (r"^my assigned lots?$", "lookup_assigned_lots"),
    (r"^search farmer\s+(.+)", "lookup_search_farmer"),
    (r"^provenance.*lot\s+(.+)", "lookup_provenance"),
    (r"^provenance check\s+(.+)", "lookup_provenance"),
    (r"^operational summary$", "lookup_operational_summary"),
    (r"^pending actions?$", "lookup_pending_actions"),
    (r"^summarize disputes?$", "lookup_dispute_queue"),
    (r"^forecast$", "lookup_forecast_summary"),
    (r"^my forecast$", "lookup_forecast_summary"),
    (r"^portfolio forecast$", "lookup_portfolio_forecast"),
    (r"^portfolio alerts?$", "lookup_portfolio_alerts"),
    (r"^my alerts?$", "lookup_my_alerts"),
    (r"^open alerts?$", "lookup_my_alerts"),
    (r"^explain alert\s+([0-9a-f-]{36})$", "lookup_explain_alert"),
    (r"^open case\s+([0-9a-f-]{36})$", "lookup_open_case"),
    (r"^search anomalies?$", "lookup_search_anomalies"),
    (r"^export case\s+([0-9a-f-]{36})$", "lookup_export_case"),
]


def detect_intent(body: str, contact: WhatsAppContact) -> dict:
    """
    Detect the user's intent from the message body.
    Returns: {"type": "workflow"|"lookup"|"cancel"|"help"|"ai_query",
              "intent": str, "conv_type": str|None, "match_groups": tuple, "confidence": float}
    """
    b = body.strip().lower()

    if b in ("cancel", "stop", "quit", "exit"):
        return {"type": "cancel", "intent": "cancel", "confidence": 1.0}

    if b in ("hi", "hello", "hey", "help", "menu", "start"):
        return {"type": "help", "intent": "help", "confidence": 1.0}

    if b.startswith("lang ") or b.startswith("language "):
        parts = b.split()
        if len(parts) >= 2 and parts[-1] in ("en", "sn", "nd"):
            return {"type": "lang", "intent": "set_lang", "lang": parts[-1], "confidence": 1.0}

    role = contact.linked_role
    intent_map = {}
    if role == UserRole.SMALLHOLDER_FARMER:
        intent_map = FARMER_INTENTS
    elif role == UserRole.BUYER_CONTRACTOR:
        intent_map = {**FARMER_INTENTS, **BUYER_INTENTS}
    else:
        intent_map = {**FARMER_INTENTS, **BUYER_INTENTS}

    for keyword, conv_type in intent_map.items():
        if b == keyword or b.startswith(keyword + " "):
            return {
                "type": "workflow",
                "intent": keyword,
                "conv_type": conv_type,
                "confidence": 1.0,
            }

    for pattern, lookup_name in LOOKUP_PATTERNS:
        match = re.match(pattern, b)
        if match:
            return {
                "type": "lookup",
                "intent": lookup_name,
                "match_groups": match.groups(),
                "confidence": 1.0,
            }

    if b.startswith("talk to assistant") or b.startswith("ask ai") or b.startswith("ai "):
        return {"type": "ai_query", "intent": "ai_query", "query": body.strip(), "confidence": 0.9}

    return {"type": "ai_query", "intent": "ai_fallback", "query": body.strip(), "confidence": 0.3}


def route_message(contact: WhatsAppContact, body: str, media_url: str = None) -> str:
    """
    Main entry point for routing a WhatsApp message.
    Handles active conversations, new intents, lookups, and AI fallback.
    """
    active_conv = get_active_conversation(contact)

    if media_url and active_conv:
        active_conv.state_data["media_url"] = media_url
        active_conv.state_data["media_type"] = "image"
        active_conv.save(update_fields=["state_data", "updated_at"])

        if active_conv.current_state in ("AWAITING_MEDIA", "AWAITING_EVIDENCE"):
            active_conv.state_data["evidence_media_url"] = media_url
            active_conv.save(update_fields=["state_data"])
            from apps.whatsapp.workflows.base import Reply
            workflow = _get_workflow(active_conv.conversation_type)
            if workflow:
                reply = workflow.process(active_conv, body)
                _log_intent(active_conv, "media_received", 1.0, workflow.get_name())
                if reply.end_conversation:
                    end_conversation(active_conv)
                return reply.text

    if media_url and not active_conv:
        conv = start_conversation(contact, ConversationType.DOCUMENT_UPLOAD, "MEDIA_RECEIVED")
        conv.state_data = {"media_url": media_url, "media_type": "image"}
        conv.save(update_fields=["state_data"])
        from apps.whatsapp.workflows.document_upload import DocumentUploadWorkflow
        wf = DocumentUploadWorkflow()
        reply = wf.process(conv, body)
        _log_intent(conv, "media_upload", 1.0, "document_upload")
        if reply.end_conversation:
            end_conversation(conv)
        return reply.text

    intent = detect_intent(body, contact)

    if intent["type"] == "cancel":
        if active_conv:
            end_conversation(active_conv)
        return _help_menu(contact)

    if intent["type"] == "help":
        if active_conv:
            end_conversation(active_conv)
        return _help_menu(contact)

    if intent["type"] == "lang":
        contact.preferred_language = intent["lang"]
        contact.save(update_fields=["preferred_language", "updated_at"])
        user = contact.user
        if user:
            from apps.common.org_utils import get_user_primary_organization
            from apps.worldready.models import UserPreference

            org = get_user_primary_organization(user)
            if org:
                UserPreference.objects.update_or_create(
                    user=user,
                    organization=org,
                    defaults={"preferred_language": intent["lang"]},
                )
        from apps.worldready.services.translation import resolve_whatsapp_language, t

        lang = resolve_whatsapp_language(contact)
        oid = None
        if user:
            from apps.common.org_utils import get_user_primary_organization

            o = get_user_primary_organization(user)
            oid = o.id if o else None
        return t("lang.set_ok", lang, organization_id=oid, code=intent["lang"])

    if active_conv and intent["type"] != "workflow":
        workflow = _get_workflow(active_conv.conversation_type)
        if workflow:
            reply = workflow.process(active_conv, body)
            _log_intent(active_conv, active_conv.current_intent or "continuation", 1.0, workflow.get_name())
            if reply.end_conversation:
                end_conversation(active_conv)
            return reply.text

    if intent["type"] == "workflow":
        if active_conv:
            end_conversation(active_conv)
        conv = start_conversation(contact, intent["conv_type"], "INIT")
        conv.current_intent = intent["intent"]
        conv.save(update_fields=["current_intent"])
        workflow = _get_workflow(intent["conv_type"])
        if workflow:
            reply = workflow.process(conv, body)
            _log_intent(conv, intent["intent"], intent["confidence"], workflow.get_name())
            if reply.end_conversation:
                end_conversation(conv)
            return reply.text
        return "This workflow is not yet available."

    if intent["type"] == "lookup":
        _log_intent(None, intent["intent"], intent["confidence"], "lookup")
        return _handle_lookup(contact, intent)

    if intent["type"] == "ai_query":
        _log_intent(None, intent["intent"], intent["confidence"], "ai_service")
        return _handle_ai_query(contact, intent.get("query", body))

    return _help_menu(contact)


def _get_workflow(conv_type: str):
    from apps.whatsapp.workflows.farmer_onboarding import FarmerOnboardingWorkflow
    from apps.whatsapp.workflows.farm_registration import FarmRegistrationWorkflow
    from apps.whatsapp.workflows.lot_and_events import EventCaptureWorkflow, LotCreationWorkflow
    from apps.whatsapp.workflows.document_upload import DocumentUploadWorkflow
    from apps.whatsapp.workflows.dispute_workflow import DisputeCreationWorkflow
    from apps.whatsapp.workflows.buyer_workflows import (
        BuyerDisputeResponseWorkflow,
        BuyerGradingWorkflow,
        BuyerSaleWorkflow,
        BuyerSettlementUpdateWorkflow,
    )

    mapping = {
        ConversationType.ONBOARDING: FarmerOnboardingWorkflow,
        ConversationType.FARM_REGISTRATION: FarmRegistrationWorkflow,
        ConversationType.LOT_CREATION: LotCreationWorkflow,
        ConversationType.EVENT_CAPTURE: EventCaptureWorkflow,
        ConversationType.DOCUMENT_UPLOAD: DocumentUploadWorkflow,
        ConversationType.DISPUTE_CREATION: DisputeCreationWorkflow,
        ConversationType.GRADING: BuyerGradingWorkflow,
        ConversationType.SALE_RECORDING: BuyerSaleWorkflow,
        ConversationType.SETTLEMENT: BuyerSettlementUpdateWorkflow,
        ConversationType.DISPUTE_RESPONSE: BuyerDisputeResponseWorkflow,
    }

    cls = mapping.get(conv_type)
    return cls() if cls else None


def _handle_lookup(contact: WhatsAppContact, intent: dict) -> str:
    name = intent["intent"]
    groups = intent.get("match_groups", ())
    user = contact.user

    if not user:
        return "You must be registered to use this feature. Type REGISTER to get started."

    if name == "lookup_settlements":
        return _lookup_settlements(user)
    elif name == "lookup_trace_lot":
        return _lookup_trace_lot(user, groups[0] if groups else "")
    elif name == "lookup_verify_document":
        return _lookup_verify_document(user, groups[0] if groups else "")
    elif name == "lookup_dispute_status":
        dispute_id = groups[0] if groups and groups[0] else None
        return _lookup_dispute_status(user, dispute_id)
    elif name == "lookup_my_lots":
        return _lookup_my_lots(user)
    elif name == "lookup_my_documents":
        return _lookup_my_documents(user)
    elif name == "lookup_assigned_lots":
        return _lookup_assigned_lots(user)
    elif name == "lookup_search_farmer":
        return _lookup_search_farmer(user, groups[0] if groups else "")
    elif name == "lookup_provenance":
        return _lookup_provenance(user, groups[0] if groups else "")
    elif name == "lookup_operational_summary":
        return _lookup_operational_summary(user)
    elif name == "lookup_pending_actions":
        return _lookup_pending_actions(user)
    elif name == "lookup_dispute_queue":
        return _lookup_dispute_queue(user)
    elif name == "lookup_forecast_summary":
        return _lookup_forecast_summary(user, contact)
    elif name == "lookup_portfolio_forecast":
        return _lookup_portfolio_forecast(user, contact)
    elif name == "lookup_portfolio_alerts":
        return _lookup_portfolio_alerts(user, contact)
    elif name == "lookup_my_alerts":
        return _lookup_my_alerts(user, contact)
    elif name == "lookup_explain_alert":
        return _lookup_explain_alert(user, groups[0] if groups else "")
    elif name == "lookup_open_case":
        return _lookup_open_case(user, groups[0] if groups else "")
    elif name == "lookup_search_anomalies":
        return _lookup_search_anomalies(user, contact)
    elif name == "lookup_export_case":
        return _lookup_export_case(user, groups[0] if groups else "")

    return "This lookup is not yet available."


def _handle_ai_query(contact: WhatsAppContact, query: str) -> str:
    user = contact.user
    if not user:
        return "You must be registered to use the AI assistant. Type REGISTER."

    try:
        from apps.ai_assistant.services import process_ai_query
        result = process_ai_query(user=user, prompt=query)
        answer = result.get("response", "I wasn't able to understand that. Try rephrasing or type HELP.")

        from apps.audit.services import log_audit
        log_audit(
            actor=user,
            action="WHATSAPP_AI_QUERY",
            resource_type="AIInteraction",
            description=f"WhatsApp AI query: {query[:100]}",
        )

        return answer
    except Exception:
        logger.exception("AI query failed for WhatsApp user %s", user.id)
        return (
            "I couldn't process your question right now. "
            "Try a specific command like MY SETTLEMENTS or HELP."
        )


def _log_intent(conv, intent: str, confidence: float, handler: str, ai_used: bool = False):
    try:
        WhatsAppIntentLog.objects.create(
            conversation=conv,
            detected_intent=intent,
            confidence=confidence,
            routed_handler=handler,
            ai_used=ai_used,
        )
    except Exception:
        logger.exception("Failed to log intent")


def _help_menu(contact: WhatsAppContact) -> str:
    from apps.common.org_utils import get_user_primary_organization
    from apps.worldready.services.translation import resolve_whatsapp_language, t

    user = contact.user
    name = user.first_name if user else "there"
    role = contact.linked_role
    lang = resolve_whatsapp_language(contact)
    oid = None
    if user:
        org = get_user_primary_organization(user)
        oid = org.id if org else None

    lines = [
        f"Hello {name}! Zimbabwe Tobacco Platform",
        t("menu.header", lang, organization_id=oid),
        t("menu.help", lang, organization_id=oid),
        "LANG EN | LANG SN | LANG ND — set language\n",
    ]

    if not user:
        lines.append("Commands:")
        lines.append("- REGISTER — create your account")
        lines.append("- HELP — show this menu")
        return "\n".join(lines)

    lines.append("Commands:\n")

    if role == UserRole.SMALLHOLDER_FARMER or not role:
        lines.extend([
            "Farm & Lots:",
            "- REGISTER FARM — register a new farm",
            "- CREATE LOT — create a new lot",
            "- ADD EVENT — record a traceability event",
            "- VIEW LOTS — see your lots\n",
            "Documents:",
            "- UPLOAD DOCUMENT — upload receipt/certificate",
            "- MY DOCUMENTS — view your documents\n",
            "Payments:",
            "- MY SETTLEMENTS — check payment status",
            "- MY PAYMENT — same as above\n",
            "Disputes:",
            "- RAISE DISPUTE — start a new dispute",
            "- DISPUTE STATUS — check dispute\n",
            "AI & alerts:",
            "- FORECAST — yield/price snapshot (your data only)",
            "- MY ALERTS — open anomalies",
            "- EXPLAIN ALERT <id> — summary + actions\n",
            "Other:",
            "- TRACE LOT <code> — trace a lot",
            "- TALK TO ASSISTANT — ask AI a question",
            "- CANCEL — cancel current action",
        ])

    if role == UserRole.BUYER_CONTRACTOR:
        lines.extend([
            "Buyer Operations:",
            "- RECORD GRADING — grade a lot",
            "- RECORD SALE — record a sale",
            "- UPDATE SETTLEMENT — update payment status",
            "- MY ASSIGNED LOTS — view your lots\n",
            "Disputes:",
            "- RESPOND DISPUTE — respond to a dispute",
            "- SUMMARIZE DISPUTES — dispute queue\n",
            "Analytics:",
            "- OPERATIONAL SUMMARY — overview",
            "- PENDING ACTIONS — pending items",
            "- PORTFOLIO FORECAST — assigned lots summary",
            "- PORTFOLIO ALERTS — open anomalies on assigned lots",
            "- OPEN CASE <uuid> — case summary + app link",
            "- PROVENANCE CHECK <lot> — check provenance\n",
            "Documents:",
            "- UPLOAD GRADING SHEET — upload docs",
            "- SEARCH FARMER <name> — find a farmer\n",
            "Other:",
            "- TALK TO ASSISTANT — ask AI",
            "- CANCEL — cancel current action",
        ])

    if role == UserRole.REGULATOR_AUDITOR:
        lines.extend([
            "Auditor:",
            "- SEARCH ANOMALIES — recent org alerts",
            "- EXPORT CASE <uuid> — signed export link (short-lived)",
            "- TALK TO ASSISTANT — scoped audit tools",
        ])

    return "\n".join(lines)


# ────────────────────────────────────────────────────────────
# Lookup handlers
# ────────────────────────────────────────────────────────────

def _lookup_settlements(user) -> str:
    from apps.settlements.models import Settlement
    if user.role == UserRole.SMALLHOLDER_FARMER:
        qs = Settlement.objects.filter(farmer=user)
    elif user.role == UserRole.BUYER_CONTRACTOR:
        qs = Settlement.objects.filter(created_by=user)
    else:
        return "Settlement lookup is available for Farmers and Buyers."

    settlements = qs.select_related("sale", "sale__lot").order_by("-created_at")[:5]
    if not settlements:
        return "You have no settlements on record."

    lines = ["Your recent settlements:\n"]
    for s in settlements:
        lot_num = s.sale.lot.lot_number if s.sale and s.sale.lot else "N/A"
        lines.append(
            f"• Lot {lot_num} — Due: ${s.amount_due}, "
            f"Paid: ${s.amount_paid}, Status: {s.status}"
        )
    return "\n".join(lines)


def _lookup_trace_lot(user, lot_code: str) -> str:
    from apps.lots.models import Lot
    from apps.traceability.models import TraceEvent

    lot = Lot.objects.filter(lot_number__iexact=lot_code.strip()).first()
    if not lot:
        return f"Lot '{lot_code}' not found."

    events = TraceEvent.objects.filter(lot=lot).order_by("timestamp")[:10]
    lines = [f"Lot {lot.lot_number} — Status: {lot.status}\n"]
    for e in events:
        lines.append(f"• {e.event_type} at {e.timestamp:%Y-%m-%d %H:%M}")
    if not events:
        lines.append("No trace events recorded.")
    return "\n".join(lines)


def _lookup_verify_document(user, doc_id: str) -> str:
    from apps.documents.models import Document
    doc = Document.objects.filter(id=doc_id).first() if len(doc_id) > 8 else None
    if not doc:
        return f"Document '{doc_id}' not found."
    return (
        f"Document: {doc.title}\n"
        f"Type: {doc.document_type}\n"
        f"SHA-256: {doc.sha256_hash[:16]}...\n"
        f"Blockchain: {doc.anchor_status}"
    )


def _lookup_dispute_status(user, dispute_id: str = None) -> str:
    from apps.disputes.models import Dispute
    if dispute_id:
        d = Dispute.objects.filter(id=dispute_id).first() if len(dispute_id) > 8 else None
        if not d:
            return f"Dispute '{dispute_id}' not found."
        return (
            f"Dispute: {d.title}\nStatus: {d.status}\n"
            f"Filed: {d.created_at:%Y-%m-%d}\n"
            f"Resolution: {d.resolution[:100] if d.resolution else 'Pending'}"
        )
    disputes = Dispute.objects.filter(raised_by=user).order_by("-created_at")[:5]
    if not disputes:
        return "You have no disputes on record."
    lines = ["Your disputes:\n"]
    for d in disputes:
        lines.append(f"• {d.title} — {d.status} ({d.created_at:%Y-%m-%d})")
    return "\n".join(lines)


def _lookup_my_lots(user) -> str:
    from apps.lots.models import Lot
    lots = Lot.objects.filter(farm__owner=user).order_by("-created_at")[:10]
    if not lots:
        return "You have no lots. Type CREATE LOT to get started."
    lines = ["Your lots:\n"]
    for lot in lots:
        lines.append(f"• {lot.lot_number} — {lot.status}")
    return "\n".join(lines)


def _lookup_my_documents(user) -> str:
    from apps.documents.models import Document
    docs = Document.objects.filter(uploaded_by=user).order_by("-created_at")[:10]
    if not docs:
        return "No documents found."
    lines = ["Your documents:\n"]
    for doc in docs:
        lines.append(f"• {doc.title} ({doc.document_type}) — {doc.anchor_status}")
    return "\n".join(lines)


def _lookup_assigned_lots(user) -> str:
    from apps.lots.models import Lot
    from apps.sales.models import Sale
    lot_ids = Sale.objects.filter(buyer=user).values_list("lot_id", flat=True)
    lots = Lot.objects.filter(id__in=lot_ids).order_by("-created_at")[:10]
    if not lots:
        return "No assigned lots found."
    lines = ["Assigned lots:\n"]
    for lot in lots:
        lines.append(f"• {lot.lot_number} — {lot.status}")
    return "\n".join(lines)


def _lookup_search_farmer(user, query: str) -> str:
    from django.contrib.auth import get_user_model

    from apps.common.org_utils import get_user_primary_organization
    from apps.organizations.models import OrganizationMembership

    User = get_user_model()
    org = get_user_primary_organization(user)
    if org is None:
        return "Organization context required."
    farmer_ids = OrganizationMembership.objects.filter(
        organization=org,
        role=UserRole.SMALLHOLDER_FARMER,
        is_active=True,
    ).values_list("user_id", flat=True)
    q = query.strip()
    results = User.objects.filter(
        id__in=farmer_ids,
        is_active=True,
    ).filter(
        models_Q(first_name__icontains=q) | models_Q(last_name__icontains=q)
    )[:10]
    if not results:
        return f"No farmers found matching '{q}' in your organization."
    lines = [f"Farmers matching '{q}' (your org):\n"]
    for f in results:
        lines.append(f"• {f.full_name}")
    return "\n".join(lines)


def _lookup_provenance(user, lot_code: str) -> str:
    from apps.lots.models import Lot
    lot = Lot.objects.filter(lot_number__iexact=lot_code.strip()).first()
    if not lot:
        return f"Lot '{lot_code}' not found."

    from apps.provenance.services import get_lot_provenance
    result = get_lot_provenance(str(lot.id))
    if not result:
        return f"No provenance data for lot {lot_code}."

    lines = [f"Provenance for {lot_code}:\n"]
    for event in result.get("events", [])[:8]:
        lines.append(f"• {event.get('event_type')} at {event.get('timestamp', 'N/A')}")
    docs = result.get("documents", [])
    if docs:
        lines.append(f"\nDocuments: {len(docs)} attached")
    return "\n".join(lines)


def _lookup_operational_summary(user) -> str:
    from apps.lots.models import Lot
    from apps.settlements.models import Settlement
    from apps.disputes.models import Dispute
    from apps.common.enums import SettlementStatus, DisputeStatus

    if user.role == UserRole.BUYER_CONTRACTOR:
        from apps.sales.models import Sale
        total_sales = Sale.objects.filter(buyer=user).count()
        pending_settlements = Settlement.objects.filter(
            created_by=user, status=SettlementStatus.PENDING,
        ).count()
        open_disputes = Dispute.objects.filter(
            sale__buyer=user, status__in=[DisputeStatus.OPEN, DisputeStatus.UNDER_REVIEW],
        ).count()
        return (
            f"Operational Summary:\n\n"
            f"Total Sales: {total_sales}\n"
            f"Pending Settlements: {pending_settlements}\n"
            f"Open Disputes: {open_disputes}"
        )

    farms_count = 0
    from apps.farms.models import Farm
    farms_count = Farm.objects.filter(owner=user).count()
    lots_count = Lot.objects.filter(farm__owner=user).count()
    return f"Summary:\nFarms: {farms_count}\nLots: {lots_count}"


def _lookup_pending_actions(user) -> str:
    lines = ["Pending actions:\n"]
    from apps.settlements.models import Settlement
    from apps.common.enums import SettlementStatus
    pending = Settlement.objects.filter(
        created_by=user, status=SettlementStatus.PENDING,
    ).count()
    lines.append(f"• Pending settlements: {pending}")

    from apps.disputes.models import Dispute
    from apps.common.enums import DisputeStatus
    open_d = Dispute.objects.filter(
        sale__buyer=user, status=DisputeStatus.OPEN,
    ).count()
    lines.append(f"• Open disputes: {open_d}")
    return "\n".join(lines)


def _lookup_dispute_queue(user) -> str:
    from apps.disputes.models import Dispute
    from apps.common.enums import DisputeStatus
    disputes = Dispute.objects.filter(
        sale__buyer=user,
        status__in=[DisputeStatus.OPEN, DisputeStatus.UNDER_REVIEW],
    ).order_by("-created_at")[:10]
    if not disputes:
        return "No open disputes in your queue."
    lines = ["Dispute queue:\n"]
    for d in disputes:
        lines.append(f"• {d.title} — {d.status}")
    return "\n".join(lines)


def _band_confidence_pct(yhat, lo, hi) -> int:
    try:
        y, a, b = float(yhat), float(lo), float(hi)
        width = b - a
        if width <= 0:
            return 50
        rel = width / max(abs(y), 1e-6)
        return max(0, min(100, int(100 / (1 + rel * 2))))
    except Exception:
        return 50


def _lookup_forecast_summary(user, contact: WhatsAppContact) -> str:
    from apps.ai_intelligence.services.forecast_service import ForecastService
    from apps.whatsapp.deep_links import forecast_link

    if contact.linked_role == UserRole.BUYER_CONTRACTOR:
        return "Use PORTFOLIO FORECAST for your assigned lots."
    if contact.linked_role == UserRole.REGULATOR_AUDITOR:
        return "Org-wide forecasts are available in the app or assistant."

    y = ForecastService.list_yield_forecasts(user)[:3]
    p = ForecastService.list_price_forecasts(user)[:3]
    lines = ["Forecast (your data only)\n"]
    if y:
        pt = y[0]
        conf = _band_confidence_pct(pt["yhat"], pt["yhat_lower"], pt["yhat_upper"])
        lines.append(
            f"Yield: {pt['yhat']} (band {pt['yhat_lower']}–{pt['yhat_upper']})\n"
            f"Confidence: ~{conf}%"
        )
    else:
        lines.append("Yield: no recent forecast points.")
    if p:
        pt = p[0]
        conf = _band_confidence_pct(pt["yhat"], pt["yhat_lower"], pt["yhat_upper"])
        lines.append(
            f"\nPrice: {pt['yhat']} (band {pt['yhat_lower']}–{pt['yhat_upper']})\n"
            f"Confidence: ~{conf}%"
        )
    else:
        lines.append("\nPrice: no recent forecast points.")
    lines.append(f"\nView in app:\n{forecast_link('yield')}")
    return "\n".join(lines)


def _lookup_portfolio_forecast(user, contact: WhatsAppContact) -> str:
    from apps.ai_intelligence.services.forecast_service import ForecastService
    from apps.whatsapp.deep_links import forecast_link

    if contact.linked_role != UserRole.BUYER_CONTRACTOR:
        return "PORTFOLIO FORECAST is for buyers only."
    y = ForecastService.list_yield_forecasts(user)[:5]
    p = ForecastService.list_price_forecasts(user)[:5]
    lines = ["Portfolio forecast (assigned scope)\n"]
    lines.append(f"Yield points: {len(y)} | Price points: {len(p)}")
    if y:
        pt = y[0]
        lines.append(f"\nLatest yield: {pt['yhat']} (LOW/MED/HIGH band in app)")
    lines.append(f"\n{forecast_link('yield', scope='portfolio')}")
    return "\n".join(lines)


def _lookup_portfolio_alerts(user, contact: WhatsAppContact) -> str:
    from apps.ai_intelligence.services.anomaly_service import AnomalyService
    from apps.whatsapp.deep_links import anomaly_link

    if contact.linked_role != UserRole.BUYER_CONTRACTOR:
        return "PORTFOLIO ALERTS is for buyers only."
    rows = AnomalyService.list_alerts(user, status="OPEN")[:8]
    if not rows:
        return "No open alerts on your assigned lots."
    lines = ["Open alerts (assigned lots)\n"]
    for a in rows:
        lines.append(
            f"• {a['severity']}: {a.get('title') or a['alert_type']}\n"
            f"  {anomaly_link(a['id'])}"
        )
    return "\n".join(lines)


def _lookup_my_alerts(user, contact: WhatsAppContact) -> str:
    from apps.ai_intelligence.services.anomaly_service import AnomalyService
    from apps.whatsapp.deep_links import anomaly_link

    if contact.linked_role == UserRole.BUYER_CONTRACTOR:
        return "Use PORTFOLIO ALERTS, or type OPEN CASE <id>."
    rows = [a for a in AnomalyService.list_alerts(user, status="OPEN")][:8]
    if not rows:
        return "No open alerts. Use the app for history and actions."
    lines = ["Your open alerts\n"]
    for a in rows:
        lines.append(
            f"• {a['severity']}: {a.get('title') or a['alert_type']}\n"
            f"  {anomaly_link(a['id'])}"
        )
    return "\n".join(lines)


def _lookup_explain_alert(user, alert_id: str) -> str:
    from uuid import UUID

    from apps.ai_intelligence.services.anomaly_service import AnomalyService
    from apps.whatsapp.deep_links import anomaly_link

    try:
        aid = UUID(alert_id.strip())
    except ValueError:
        return "Invalid alert id. Use EXPLAIN ALERT <uuid>."
    packet = AnomalyService.case_packet(user, aid)
    if not packet:
        return "Alert not found or not visible to you."
    alert = packet.get("alert") or {}
    sev = alert.get("severity", "?")
    title = alert.get("title") or alert.get("alert_type", "Alert")
    lines = [
        f"{title}",
        f"Severity: {sev}",
        "Evidence is available in the app (PII-safe summary here).",
        f"\n{anomaly_link(aid)}",
    ]
    return "\n".join(lines)


def _lookup_open_case(user, alert_id: str) -> str:
    return _lookup_explain_alert(user, alert_id)


def _lookup_search_anomalies(user, contact: WhatsAppContact) -> str:
    from apps.ai_intelligence.services.anomaly_service import AnomalyService
    from apps.whatsapp.deep_links import anomaly_link

    if contact.linked_role not in (UserRole.REGULATOR_AUDITOR, UserRole.SYSTEM_ADMIN):
        return "SEARCH ANOMALIES is for auditors/admins."
    rows = AnomalyService.list_alerts(user)[:15]
    if not rows:
        return "No anomalies in your org scope."
    lines = ["Recent anomalies (org)\n"]
    for a in rows:
        lines.append(f"• {a['severity']}: {a.get('title') or a['alert_type']}\n  {anomaly_link(a['id'])}")
    return "\n".join(lines)


def _lookup_export_case(user, alert_id: str) -> str:
    from uuid import UUID

    from django.conf import settings

    from apps.ai_intelligence.export_signed import (
        MAX_AGE_SECONDS,
        build_export_download_url_public,
        sign_export_payload,
    )
    from apps.ai_intelligence.services.anomaly_service import AnomalyService

    if user.role not in (UserRole.REGULATOR_AUDITOR, UserRole.SYSTEM_ADMIN):
        return "EXPORT CASE is for auditors/admins only."
    try:
        aid = UUID(alert_id.strip())
    except ValueError:
        return "Invalid id. Use EXPORT CASE <uuid>."
    if AnomalyService.case_packet(user, aid) is None:
        return "Case not found or not visible."
    base = getattr(settings, "PUBLIC_API_BASE_URL", "") or ""
    if not base:
        return "Server missing PUBLIC_API_BASE_URL; cannot build export link."
    token = sign_export_payload(alert_id=aid, user_id=user.id)
    url = build_export_download_url_public(base, token)
    return (
        f"Export (expires in {MAX_AGE_SECONDS // 60} min):\n{url}\n"
        "Do not share this link."
    )


def route_inbound_message(phone: str, body: str, media_url: str | None = None) -> str:
    """
    Resolve WhatsAppContact by phone and route the message.
    Used by tests and tooling; the HTTP webhook uses route_message() with an existing contact.
    """
    from apps.whatsapp.session_service import get_or_create_contact

    contact = get_or_create_contact(phone)
    return route_message(contact, body, media_url=media_url)


def models_Q(*args, **kwargs):
    """Helper to avoid top-level import of Q."""
    from django.db.models import Q
    return Q(*args, **kwargs)
