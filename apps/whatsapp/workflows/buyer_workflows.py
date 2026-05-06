"""
Buyer / Contractor workflows via WhatsApp.

1. BuyerGradingWorkflow: Record grading for a lot.
2. BuyerSaleWorkflow: Record a sale and create settlement.
3. BuyerSettlementUpdateWorkflow: Update payment status on a settlement.
4. BuyerDisputeResponseWorkflow: Respond to a dispute.
"""
import logging
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

from apps.common.enums import DisputeStatus, LotStatus, SettlementStatus, TraceEventType
from apps.whatsapp.session_service import advance_state, end_conversation
from apps.whatsapp.workflows.base import BaseWorkflow, Reply

logger = logging.getLogger(__name__)


class BuyerGradingWorkflow(BaseWorkflow):

    def get_name(self) -> str:
        return "buyer_grading"

    def handle_init(self, conv, body, contact):
        user = contact.user
        if not user:
            end_conversation(conv)
            return Reply("You must be registered. Contact your admin.", end_conversation=True)

        from apps.lots.models import Lot
        lots = list(
            Lot.objects.filter(
                status__in=[LotStatus.REGISTERED, LotStatus.CURED],
            ).order_by("-created_at")[:15]
        )
        if not lots:
            end_conversation(conv)
            return Reply("No lots available for grading.", end_conversation=True)

        lot_list = []
        lot_ids = []
        for i, lot in enumerate(lots, 1):
            lot_list.append(f"{i}. {lot.lot_number} ({lot.status})")
            lot_ids.append(str(lot.id))

        advance_state(conv, "SELECT_LOT", {"lot_ids": lot_ids})
        return Reply("Select a lot to grade:\n" + "\n".join(lot_list))

    def handle_select_lot(self, conv, body, contact):
        ids = conv.state_data.get("lot_ids", [])
        choice = self._parse_choice(body, len(ids))
        if not choice:
            return Reply(f"Please enter a number between 1 and {len(ids)}:")
        advance_state(conv, "ASK_GRADE", {"lot_id": ids[choice - 1]})
        return Reply("Enter the grade (e.g. A1, B2, C3):")

    def handle_ask_grade(self, conv, body, contact):
        grade = body.strip().upper()
        if len(grade) < 1:
            return Reply("Please enter a valid grade:")
        advance_state(conv, "ASK_WEIGHT", {"grade": grade})
        return Reply("Enter weight in kg:")

    def handle_ask_weight(self, conv, body, contact):
        try:
            weight = Decimal(body.strip())
            if weight <= 0:
                raise InvalidOperation
        except (InvalidOperation, ValueError):
            return Reply("Please enter a valid weight in kg:")
        advance_state(conv, "ASK_BALES", {"weight_kg": str(weight)})
        return Reply("How many bales?")

    def handle_ask_bales(self, conv, body, contact):
        try:
            bales = int(body.strip())
            if bales <= 0:
                raise ValueError
        except ValueError:
            return Reply("Please enter a valid number of bales:")
        advance_state(conv, "ASK_NOTES", {"bale_count": bales})
        return Reply("Add quality notes (or type SKIP):")

    def handle_ask_notes(self, conv, body, contact):
        notes = "" if body.strip().lower() == "skip" else body.strip()
        advance_state(conv, "CONFIRM", {"notes": notes})
        d = conv.state_data
        return Reply(
            "Confirm grading:\n\n"
            f"Grade: {d['grade']}\n"
            f"Weight: {d['weight_kg']} kg\n"
            f"Bales: {d['bale_count']}\n"
            f"Notes: {notes or 'N/A'}\n\n"
            "Reply YES to submit or NO to cancel."
        )

    def handle_confirm(self, conv, body, contact):
        if body.strip().lower() not in ("yes", "y"):
            end_conversation(conv)
            return Reply("Grading cancelled.", end_conversation=True)

        d = conv.state_data
        with transaction.atomic():
            from apps.grading.models import GradeRecord
            record = GradeRecord.objects.create(
                lot_id=d["lot_id"],
                graded_by=contact.user,
                grade=d["grade"],
                weight_kg=Decimal(d["weight_kg"]),
                notes=d.get("notes", ""),
                graded_at=timezone.now(),
            )
            from apps.lots.models import Lot
            Lot.objects.filter(id=d["lot_id"]).update(status=LotStatus.GRADED)

            from apps.traceability.models import TraceEvent
            TraceEvent.objects.create(
                lot_id=d["lot_id"],
                actor=contact.user,
                event_type=TraceEventType.GRADING,
                timestamp=timezone.now(),
                payload={"grade": d["grade"], "weight_kg": d["weight_kg"], "source": "whatsapp"},
            )

        from apps.audit.services import log_audit
        log_audit(
            actor=contact.user,
            action="WHATSAPP_GRADING_RECORDED",
            resource_type="GradeRecord",
            resource_id=str(record.id),
            description=f"Grade {d['grade']} recorded via WhatsApp",
        )

        end_conversation(conv)
        return Reply(
            f"Grading recorded: {d['grade']} @ {d['weight_kg']} kg\n"
            "Type RECORD SALE to proceed to sale.",
            end_conversation=True,
        )


class BuyerSaleWorkflow(BaseWorkflow):

    def get_name(self) -> str:
        return "buyer_sale"

    def handle_init(self, conv, body, contact):
        user = contact.user
        if not user:
            end_conversation(conv)
            return Reply("You must be registered.", end_conversation=True)

        from apps.lots.models import Lot
        lots = list(
            Lot.objects.filter(status=LotStatus.GRADED).order_by("-created_at")[:15]
        )
        if not lots:
            end_conversation(conv)
            return Reply("No graded lots available for sale.", end_conversation=True)

        lot_list = []
        lot_ids = []
        for i, lot in enumerate(lots, 1):
            lot_list.append(f"{i}. {lot.lot_number}")
            lot_ids.append(str(lot.id))

        advance_state(conv, "SELECT_LOT", {"lot_ids": lot_ids})
        return Reply("Select a graded lot to record sale:\n" + "\n".join(lot_list))

    def handle_select_lot(self, conv, body, contact):
        ids = conv.state_data.get("lot_ids", [])
        choice = self._parse_choice(body, len(ids))
        if not choice:
            return Reply(f"Please enter a number between 1 and {len(ids)}:")
        advance_state(conv, "ASK_PRICE", {"lot_id": ids[choice - 1]})
        return Reply("Enter price per kg (USD):")

    def handle_ask_price(self, conv, body, contact):
        try:
            price = Decimal(body.strip())
            if price <= 0:
                raise InvalidOperation
        except (InvalidOperation, ValueError):
            return Reply("Please enter a valid price per kg:")
        advance_state(conv, "ASK_TOTAL_WEIGHT", {"price_per_kg": str(price)})
        return Reply("Enter total weight being sold (kg):")

    def handle_ask_total_weight(self, conv, body, contact):
        try:
            weight = Decimal(body.strip())
            if weight <= 0:
                raise InvalidOperation
        except (InvalidOperation, ValueError):
            return Reply("Please enter a valid weight:")

        price = Decimal(conv.state_data["price_per_kg"])
        total = price * weight
        advance_state(conv, "CONFIRM", {
            "total_weight_kg": str(weight),
            "total_amount": str(total),
        })
        return Reply(
            "Confirm sale:\n\n"
            f"Price: ${price}/kg\n"
            f"Weight: {weight} kg\n"
            f"Total: ${total}\n\n"
            "Reply YES to confirm or NO to cancel."
        )

    def handle_confirm(self, conv, body, contact):
        if body.strip().lower() not in ("yes", "y"):
            end_conversation(conv)
            return Reply("Sale cancelled.", end_conversation=True)

        d = conv.state_data
        with transaction.atomic():
            from apps.sales.models import Sale
            sale = Sale.objects.create(
                lot_id=d["lot_id"],
                buyer=contact.user,
                price_per_kg=Decimal(d["price_per_kg"]),
                total_weight_kg=Decimal(d["total_weight_kg"]),
                total_amount=Decimal(d["total_amount"]),
                sale_date=timezone.now(),
            )
            from apps.lots.models import Lot
            lot = Lot.objects.get(id=d["lot_id"])
            lot.status = LotStatus.SOLD
            lot.save(update_fields=["status", "updated_at"])

            from apps.settlements.models import Settlement
            Settlement.objects.create(
                sale=sale,
                farmer=lot.farm.owner,
                created_by=contact.user,
                amount_due=Decimal(d["total_amount"]),
                currency="USD",
                status=SettlementStatus.PENDING,
            )

            from apps.traceability.models import TraceEvent
            TraceEvent.objects.create(
                lot_id=d["lot_id"],
                actor=contact.user,
                event_type=TraceEventType.SALE,
                timestamp=timezone.now(),
                payload={
                    "price_per_kg": d["price_per_kg"],
                    "total_amount": d["total_amount"],
                    "source": "whatsapp",
                },
            )

        from apps.audit.services import log_audit
        log_audit(
            actor=contact.user,
            action="WHATSAPP_SALE_RECORDED",
            resource_type="Sale",
            resource_id=str(sale.id),
            description=f"Sale of ${d['total_amount']} recorded via WhatsApp",
        )

        from apps.whatsapp.tasks import send_whatsapp_message_task
        farmer = lot.farm.owner
        if farmer.phone_number:
            send_whatsapp_message_task.delay(
                to=farmer.phone_number,
                body=(
                    f"Your lot {lot.lot_number} has been sold!\n"
                    f"Amount: ${d['total_amount']}\n"
                    "Check MY SETTLEMENTS for payment updates."
                ),
                user_id=str(farmer.id),
            )

        end_conversation(conv)
        return Reply(
            f"Sale recorded! Amount: ${d['total_amount']}\n"
            f"Settlement created for farmer.",
            end_conversation=True,
        )


class BuyerSettlementUpdateWorkflow(BaseWorkflow):

    def get_name(self) -> str:
        return "buyer_settlement_update"

    def handle_init(self, conv, body, contact):
        user = contact.user
        if not user:
            end_conversation(conv)
            return Reply("You must be registered.", end_conversation=True)

        from apps.settlements.models import Settlement
        settlements = list(
            Settlement.objects.filter(
                created_by=user,
                status__in=[SettlementStatus.PENDING, SettlementStatus.PARTIAL],
            ).select_related("sale", "sale__lot").order_by("-created_at")[:10]
        )
        if not settlements:
            end_conversation(conv)
            return Reply("No pending settlements to update.", end_conversation=True)

        items = []
        settle_ids = []
        for i, s in enumerate(settlements, 1):
            items.append(
                f"{i}. Lot {s.sale.lot.lot_number} — Due: ${s.amount_due} ({s.status})"
            )
            settle_ids.append(str(s.id))

        advance_state(conv, "SELECT_SETTLEMENT", {"settle_ids": settle_ids})
        return Reply("Select a settlement to update:\n" + "\n".join(items))

    def handle_select_settlement(self, conv, body, contact):
        ids = conv.state_data.get("settle_ids", [])
        choice = self._parse_choice(body, len(ids))
        if not choice:
            return Reply(f"Please enter a number between 1 and {len(ids)}:")

        advance_state(conv, "SELECT_STATUS", {"settlement_id": ids[choice - 1]})
        return Reply(
            "Update status to:\n"
            "1. Pending\n"
            "2. Partial Payment\n"
            "3. Paid\n"
            "4. On Hold"
        )

    def handle_select_status(self, conv, body, contact):
        status_map = {
            1: SettlementStatus.PENDING,
            2: SettlementStatus.PARTIAL,
            3: SettlementStatus.PAID,
            4: SettlementStatus.OVERDUE,
        }
        choice = self._parse_choice(body, 4)
        if not choice:
            return Reply("Please choose 1-4:")

        new_status = status_map[choice]
        if new_status in (SettlementStatus.PAID, SettlementStatus.PARTIAL):
            advance_state(conv, "ASK_PAYMENT_REF", {"new_status": new_status})
            return Reply("Enter payment reference (or type SKIP):")

        advance_state(conv, "CONFIRM", {"new_status": new_status})
        return Reply(
            f"Update settlement to {new_status}?\n"
            "Reply YES to confirm or NO to cancel."
        )

    def handle_ask_payment_ref(self, conv, body, contact):
        ref = "" if body.strip().lower() == "skip" else body.strip()
        advance_state(conv, "CONFIRM", {"payment_ref": ref})
        d = conv.state_data
        return Reply(
            f"Update settlement to {d['new_status']}?\n"
            f"Payment ref: {ref or 'N/A'}\n"
            "Reply YES to confirm."
        )

    def handle_confirm(self, conv, body, contact):
        if body.strip().lower() not in ("yes", "y"):
            end_conversation(conv)
            return Reply("Update cancelled.", end_conversation=True)

        d = conv.state_data
        from apps.settlements.models import Settlement
        settlement = Settlement.objects.select_related(
            "sale", "sale__lot", "farmer",
        ).get(id=d["settlement_id"])

        old_status = settlement.status
        settlement.status = d["new_status"]
        if d.get("payment_ref"):
            settlement.payment_reference = d["payment_ref"]
        if d["new_status"] == SettlementStatus.PAID:
            settlement.amount_paid = settlement.amount_due
            settlement.payment_date = timezone.now()
        settlement.save()

        from apps.audit.services import log_audit
        log_audit(
            actor=contact.user,
            action="WHATSAPP_SETTLEMENT_UPDATED",
            resource_type="Settlement",
            resource_id=str(settlement.id),
            changes={"old_status": old_status, "new_status": d["new_status"]},
            description=f"Settlement updated {old_status}->{d['new_status']} via WhatsApp",
        )

        if settlement.farmer and settlement.farmer.phone_number:
            from apps.whatsapp.tasks import send_whatsapp_message_task
            send_whatsapp_message_task.delay(
                to=settlement.farmer.phone_number,
                body=(
                    f"Settlement update for lot {settlement.sale.lot.lot_number}:\n"
                    f"Status: {d['new_status']}\n"
                    f"Amount: ${settlement.amount_due}"
                ),
                user_id=str(settlement.farmer.id),
            )

        end_conversation(conv)
        return Reply(
            f"Settlement updated to {d['new_status']}.\nFarmer has been notified.",
            end_conversation=True,
        )


class BuyerDisputeResponseWorkflow(BaseWorkflow):

    def get_name(self) -> str:
        return "buyer_dispute_response"

    def handle_init(self, conv, body, contact):
        user = contact.user
        if not user:
            end_conversation(conv)
            return Reply("You must be registered.", end_conversation=True)

        from apps.disputes.models import Dispute
        disputes = list(
            Dispute.objects.filter(
                status__in=[DisputeStatus.OPEN, DisputeStatus.UNDER_REVIEW],
                sale__buyer=user,
            ).select_related("sale", "sale__lot").order_by("-created_at")[:10]
        )
        if not disputes:
            end_conversation(conv)
            return Reply("No open disputes requiring your response.", end_conversation=True)

        items = []
        dispute_ids = []
        for i, d in enumerate(disputes, 1):
            lot_num = d.sale.lot.lot_number if d.sale else "N/A"
            items.append(f"{i}. {d.title} (Lot: {lot_num})")
            dispute_ids.append(str(d.id))

        advance_state(conv, "SELECT_DISPUTE", {"dispute_ids": dispute_ids})
        return Reply("Select a dispute to respond to:\n" + "\n".join(items))

    def handle_select_dispute(self, conv, body, contact):
        ids = conv.state_data.get("dispute_ids", [])
        choice = self._parse_choice(body, len(ids))
        if not choice:
            return Reply(f"Please enter 1-{len(ids)}:")
        advance_state(conv, "ASK_RESPONSE", {"dispute_id": ids[choice - 1]})
        return Reply("Enter your response to this dispute:")

    def handle_ask_response(self, conv, body, contact):
        response_text = body.strip()
        if len(response_text) < 5:
            return Reply("Please provide a more detailed response:")
        advance_state(conv, "ASK_ACTION", {"response_text": response_text})
        return Reply(
            "What action would you like to take?\n"
            "1. Accept & resolve dispute\n"
            "2. Reject dispute\n"
            "3. Add comment only"
        )

    def handle_ask_action(self, conv, body, contact):
        choice = self._parse_choice(body, 3)
        if not choice:
            return Reply("Please choose 1, 2, or 3:")
        action_map = {1: "resolve", 2: "reject", 3: "comment"}
        advance_state(conv, "CONFIRM", {"action": action_map[choice]})
        d = conv.state_data
        return Reply(
            f"Confirm:\nAction: {action_map[choice]}\n"
            f"Response: {d['response_text'][:100]}\n\n"
            "Reply YES to submit."
        )

    def handle_confirm(self, conv, body, contact):
        if body.strip().lower() not in ("yes", "y"):
            end_conversation(conv)
            return Reply("Cancelled.", end_conversation=True)

        d = conv.state_data
        from apps.disputes.models import Dispute, DisputeComment

        dispute = Dispute.objects.get(id=d["dispute_id"])

        DisputeComment.objects.create(
            dispute=dispute,
            author=contact.user,
            body=d["response_text"],
        )

        if d["action"] == "resolve":
            dispute.status = DisputeStatus.RESOLVED
            dispute.resolution = d["response_text"]
            dispute.resolved_at = timezone.now()
        elif d["action"] == "reject":
            dispute.status = DisputeStatus.REJECTED
            dispute.resolution = f"Rejected: {d['response_text']}"
        dispute.save()

        from apps.audit.services import log_audit
        log_audit(
            actor=contact.user,
            action="WHATSAPP_DISPUTE_RESPONSE",
            resource_type="Dispute",
            resource_id=str(dispute.id),
            description=f"Buyer responded to dispute via WhatsApp: {d['action']}",
        )

        if dispute.raised_by and dispute.raised_by.phone_number:
            from apps.whatsapp.tasks import send_whatsapp_message_task
            send_whatsapp_message_task.delay(
                to=dispute.raised_by.phone_number,
                body=f"Update on your dispute '{dispute.title}':\nStatus: {dispute.status}",
                user_id=str(dispute.raised_by.id),
            )

        end_conversation(conv)
        return Reply(
            f"Response submitted. Dispute status: {dispute.status}",
            end_conversation=True,
        )
