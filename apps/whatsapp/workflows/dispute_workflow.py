"""
Dispute creation workflow via WhatsApp (for Farmers).

States:
  INIT -> SELECT_CONTEXT -> SELECT_REASON -> ASK_EXPLANATION ->
  ASK_EVIDENCE -> CONFIRM -> DONE
"""
import logging

from django.db import transaction

from apps.common.enums import DisputeStatus
from apps.whatsapp.session_service import advance_state, end_conversation
from apps.whatsapp.workflows.base import BaseWorkflow, Reply

logger = logging.getLogger(__name__)

DISPUTE_REASONS = [
    "Incorrect grade",
    "Incorrect quantity / weight",
    "Underpayment",
    "Delayed payment",
    "Missing receipt / document",
    "Document mismatch",
    "Other",
]


class DisputeCreationWorkflow(BaseWorkflow):

    def get_name(self) -> str:
        return "dispute_creation"

    def handle_init(self, conv, body, contact):
        user = contact.user
        if not user:
            end_conversation(conv)
            return Reply("You must be registered. Type REGISTER first.", end_conversation=True)

        from apps.sales.models import Sale
        from apps.settlements.models import Settlement

        sales = list(
            Sale.objects.filter(lot__farm__owner=user)
            .select_related("lot")
            .order_by("-sale_date")[:10]
        )
        settlements = list(
            Settlement.objects.filter(farmer=user)
            .select_related("sale", "sale__lot")
            .order_by("-created_at")[:10]
        )

        options = []
        option_refs = []
        for s in sales:
            label = f"Sale: Lot {s.lot.lot_number} - {s.total_amount} {s.currency}"
            options.append(label)
            option_refs.append({"type": "sale", "id": str(s.id), "lot_id": str(s.lot_id)})
        for st in settlements:
            label = f"Settlement: {st.status} - {st.amount_due} {st.currency}"
            options.append(label)
            option_refs.append({"type": "settlement", "id": str(st.id), "sale_id": str(st.sale_id)})

        if not options:
            end_conversation(conv)
            return Reply("No sales or settlements found to dispute.", end_conversation=True)

        lines = ["What would you like to dispute?\n"]
        for i, opt in enumerate(options, 1):
            lines.append(f"{i}. {opt}")

        advance_state(conv, "SELECT_CONTEXT", {"option_refs": option_refs})
        return Reply("\n".join(lines))

    def handle_select_context(self, conv, body, contact):
        refs = conv.state_data.get("option_refs", [])
        choice = self._parse_choice(body, len(refs))
        if not choice:
            return Reply(f"Please choose a number between 1 and {len(refs)}:")

        ref = refs[choice - 1]
        advance_state(conv, "SELECT_REASON", {"dispute_ref": ref})

        lines = ["Select a reason for the dispute:\n"]
        for i, reason in enumerate(DISPUTE_REASONS, 1):
            lines.append(f"{i}. {reason}")
        return Reply("\n".join(lines))

    def handle_select_reason(self, conv, body, contact):
        choice = self._parse_choice(body, len(DISPUTE_REASONS))
        if not choice:
            return Reply(f"Please choose a number between 1 and {len(DISPUTE_REASONS)}:")

        reason = DISPUTE_REASONS[choice - 1]
        advance_state(conv, "ASK_EXPLANATION", {"reason": reason})
        return Reply(f"Reason: {reason}\nPlease describe the issue in your own words:")

    def handle_ask_explanation(self, conv, body, contact):
        explanation = body.strip()
        if len(explanation) < 5:
            return Reply("Please provide more detail about the issue:")
        advance_state(conv, "ASK_EVIDENCE", {"explanation": explanation})
        return Reply(
            "Would you like to attach evidence (photo/document)?\n"
            "1. Yes, I'll send a photo\n"
            "2. No, submit without evidence"
        )

    def handle_ask_evidence(self, conv, body, contact):
        choice = self._parse_choice(body, 2)
        if choice == 1:
            advance_state(conv, "AWAITING_EVIDENCE")
            return Reply("Send your evidence photo or document now:")
        elif choice == 2:
            advance_state(conv, "CONFIRM")
            return self._show_confirm(conv)
        return Reply("Please choose 1 or 2:")

    def handle_awaiting_evidence(self, conv, body, contact):
        if conv.state_data.get("evidence_media_url"):
            advance_state(conv, "CONFIRM")
            return self._show_confirm(conv)
        return Reply("Please send a photo or document. Or type SKIP to continue without evidence.")

    def _show_confirm(self, conv) -> Reply:
        d = conv.state_data
        ref = d.get("dispute_ref", {})
        return Reply(
            "Confirm dispute:\n\n"
            f"Against: {ref.get('type', 'N/A')} {ref.get('id', '')[:8]}...\n"
            f"Reason: {d.get('reason')}\n"
            f"Details: {d.get('explanation', '')[:100]}\n"
            f"Evidence: {'Attached' if d.get('evidence_media_url') else 'None'}\n\n"
            "Reply YES to submit or NO to cancel."
        )

    def handle_confirm(self, conv, body, contact):
        if body.strip().lower() not in ("yes", "y"):
            end_conversation(conv)
            return Reply("Dispute cancelled.", end_conversation=True)

        d = conv.state_data
        ref = d.get("dispute_ref", {})

        with transaction.atomic():
            from apps.disputes.models import Dispute
            dispute = Dispute.objects.create(
                raised_by=contact.user,
                title=f"WhatsApp Dispute: {d.get('reason', 'General')}",
                description=d.get("explanation", ""),
                status=DisputeStatus.OPEN,
                lot_id=ref.get("lot_id"),
                sale_id=ref.get("sale_id") or ref.get("id") if ref.get("type") == "sale" else None,
            )

        from apps.audit.services import log_audit
        log_audit(
            actor=contact.user,
            action="WHATSAPP_DISPUTE_CREATED",
            resource_type="Dispute",
            resource_id=str(dispute.id),
            description=f"Dispute raised via WhatsApp: {d.get('reason')}",
        )

        if d.get("evidence_media_url"):
            from apps.whatsapp.tasks import process_whatsapp_media_task
            process_whatsapp_media_task.delay(
                media_url=d["evidence_media_url"],
                media_type=d.get("evidence_media_type", ""),
                user_id=str(contact.user.id),
                doc_type="DISPUTE_EVIDENCE",
                lot_id=ref.get("lot_id"),
                phone=contact.phone_number,
            )

        end_conversation(conv)
        return Reply(
            f"Dispute submitted!\n"
            f"Dispute ID: {str(dispute.id)[:8]}...\n"
            f"Status: {dispute.status}\n\n"
            "You'll be notified when there's an update.",
            end_conversation=True,
        )
