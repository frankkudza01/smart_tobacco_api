"""
Lot creation and traceability event capture via WhatsApp.

LOT CREATION:
  INIT -> SELECT_SEASON -> ASK_LOT_NUMBER -> ASK_DESCRIPTION ->
  ASK_WEIGHT -> CONFIRM_LOT -> DONE

EVENT CAPTURE:
  INIT -> SELECT_LOT -> SELECT_EVENT_TYPE -> ASK_EVENT_NOTES ->
  CONFIRM_EVENT -> DONE
"""
import logging
import uuid

from django.db import transaction
from django.utils import timezone

from apps.common.enums import LotStatus, TraceEventType
from apps.whatsapp.session_service import advance_state, end_conversation
from apps.whatsapp.workflows.base import BaseWorkflow, Reply

logger = logging.getLogger(__name__)

EVENT_TYPE_LABELS = [
    (TraceEventType.PLANTING, "Planting"),
    (TraceEventType.FERTILIZING, "Input Received / Fertilizing"),
    (TraceEventType.HARVESTING, "Harvesting"),
    (TraceEventType.CURING, "Curing"),
    (TraceEventType.STORAGE, "Storage"),
    (TraceEventType.TRANSPORT, "Transport / Delivery Prep"),
    (TraceEventType.INSPECTION, "Inspection"),
    (TraceEventType.OTHER, "Other"),
]


class LotCreationWorkflow(BaseWorkflow):

    def get_name(self) -> str:
        return "lot_creation"

    def handle_init(self, conv, body, contact):
        user = contact.user
        if not user:
            end_conversation(conv)
            return Reply("You must be registered. Type REGISTER first.", end_conversation=True)

        from apps.seasons.models import FarmSeasonAssociation

        associations = list(
            FarmSeasonAssociation.objects.filter(farm__owner=user)
            .select_related("season", "farm")
            .order_by("-season__crop_year", "farm__name")[:10]
        )
        if not associations:
            end_conversation(conv)
            return Reply(
                "You have no farm seasons yet. Register a farm first (type REGISTER FARM).",
                end_conversation=True,
            )

        season_list = []
        association_ids = []
        for i, assoc in enumerate(associations, 1):
            season_list.append(f"{i}. {assoc.farm.name} — {assoc.season.crop_year}")
            association_ids.append(str(assoc.id))

        advance_state(conv, "SELECT_SEASON", {"association_ids": association_ids})
        return Reply("Select farm & season for the new lot:\n" + "\n".join(season_list))

    def handle_select_season(self, conv, body, contact):
        ids = conv.state_data.get("association_ids", [])
        choice = self._parse_choice(body, len(ids))
        if not choice:
            return Reply(f"Please enter a number between 1 and {len(ids)}:")

        from apps.seasons.models import FarmSeasonAssociation

        assoc = FarmSeasonAssociation.objects.select_related("season", "farm").get(pk=ids[choice - 1])
        advance_state(
            conv,
            "ASK_LOT_NUMBER",
            {"season_id": str(assoc.season_id), "farm_id": str(assoc.farm_id)},
        )
        return Reply("Enter a lot number / code (e.g. LOT-001):")

    def handle_ask_lot_number(self, conv, body, contact):
        lot_num = body.strip().upper()
        if len(lot_num) < 2:
            return Reply("Please enter a valid lot number:")

        from apps.lots.models import Lot
        if Lot.objects.filter(lot_number=lot_num).exists():
            return Reply("That lot number already exists. Please choose a different one:")

        advance_state(conv, "ASK_DESCRIPTION", {"lot_number": lot_num})
        return Reply("Enter a short description (or type SKIP):")

    def handle_ask_description(self, conv, body, contact):
        desc = "" if body.strip().lower() == "skip" else body.strip()
        advance_state(conv, "ASK_WEIGHT", {"description": desc})
        return Reply("Enter estimated weight in kg (or type SKIP):")

    def handle_ask_weight(self, conv, body, contact):
        weight = None
        if body.strip().lower() != "skip":
            try:
                weight = float(body.strip())
                if weight <= 0:
                    raise ValueError
            except ValueError:
                return Reply("Please enter a valid weight in kg, or type SKIP:")

        advance_state(conv, "CONFIRM_LOT", {"weight_kg": weight})
        d = conv.state_data
        return Reply(
            "Confirm new lot:\n\n"
            f"Lot: {d['lot_number']}\n"
            f"Description: {d.get('description') or 'N/A'}\n"
            f"Weight: {weight or 'TBD'} kg\n\n"
            "Reply YES to create or NO to cancel."
        )

    def handle_confirm_lot(self, conv, body, contact):
        if body.strip().lower() not in ("yes", "y"):
            end_conversation(conv)
            return Reply("Lot creation cancelled.", end_conversation=True)

        d = conv.state_data
        with transaction.atomic():
            from apps.lots.models import Lot
            lot = Lot.objects.create(
                season_id=d["season_id"],
                farm_id=d["farm_id"],
                created_by=contact.user,
                lot_number=d["lot_number"],
                description=d.get("description", ""),
                weight_kg=d.get("weight_kg"),
                status=LotStatus.REGISTERED,
            )

        from apps.audit.services import log_audit
        log_audit(
            actor=contact.user,
            action="WHATSAPP_LOT_CREATED",
            resource_type="Lot",
            resource_id=str(lot.id),
            description=f"Lot {lot.lot_number} created via WhatsApp",
        )

        end_conversation(conv)
        return Reply(
            f"Lot {lot.lot_number} created!\nID: {str(lot.id)[:8]}...\n\n"
            "Type ADD EVENT to record a traceability event.",
            end_conversation=True,
        )


class EventCaptureWorkflow(BaseWorkflow):

    def get_name(self) -> str:
        return "event_capture"

    def handle_init(self, conv, body, contact):
        user = contact.user
        if not user:
            end_conversation(conv)
            return Reply("You must be registered. Type REGISTER first.", end_conversation=True)

        from apps.lots.models import Lot
        lots = list(
            Lot.objects.filter(farm__owner=user)
            .order_by("-created_at")[:10]
        )
        if not lots:
            end_conversation(conv)
            return Reply("No lots found. Create a lot first (type CREATE LOT).", end_conversation=True)

        lot_list = []
        lot_ids = []
        for i, lot in enumerate(lots, 1):
            lot_list.append(f"{i}. {lot.lot_number} ({lot.status})")
            lot_ids.append(str(lot.id))

        advance_state(conv, "SELECT_LOT", {"lot_ids": lot_ids})
        return Reply("Select a lot:\n" + "\n".join(lot_list))

    def handle_select_lot(self, conv, body, contact):
        ids = conv.state_data.get("lot_ids", [])
        choice = self._parse_choice(body, len(ids))
        if not choice:
            return Reply(f"Please enter a number between 1 and {len(ids)}:")

        advance_state(conv, "SELECT_EVENT_TYPE", {"lot_id": ids[choice - 1]})

        lines = ["What type of event?\n"]
        for i, (_, label) in enumerate(EVENT_TYPE_LABELS, 1):
            lines.append(f"{i}. {label}")
        return Reply("\n".join(lines))

    def handle_select_event_type(self, conv, body, contact):
        choice = self._parse_choice(body, len(EVENT_TYPE_LABELS))
        if not choice:
            return Reply(f"Please enter a number between 1 and {len(EVENT_TYPE_LABELS)}:")

        event_type = EVENT_TYPE_LABELS[choice - 1][0]
        advance_state(conv, "ASK_EVENT_NOTES", {"event_type": event_type})
        return Reply(f"Event: {EVENT_TYPE_LABELS[choice - 1][1]}\nAdd notes or details (or type SKIP):")

    def handle_ask_event_notes(self, conv, body, contact):
        notes = "" if body.strip().lower() == "skip" else body.strip()
        advance_state(conv, "CONFIRM_EVENT", {"notes": notes})
        d = conv.state_data
        return Reply(
            "Confirm event:\n\n"
            f"Lot: {d.get('lot_id', '')[:8]}...\n"
            f"Type: {d['event_type']}\n"
            f"Notes: {notes or 'N/A'}\n\n"
            "Reply YES to submit or NO to cancel."
        )

    def handle_confirm_event(self, conv, body, contact):
        if body.strip().lower() not in ("yes", "y"):
            end_conversation(conv)
            return Reply("Event cancelled.", end_conversation=True)

        d = conv.state_data
        with transaction.atomic():
            from apps.traceability.models import TraceEvent
            event = TraceEvent.objects.create(
                lot_id=d["lot_id"],
                actor=contact.user,
                event_type=d["event_type"],
                timestamp=timezone.now(),
                notes=d.get("notes", ""),
                payload={"source": "whatsapp"},
            )

        from apps.audit.services import log_audit
        log_audit(
            actor=contact.user,
            action="WHATSAPP_TRACE_EVENT",
            resource_type="TraceEvent",
            resource_id=str(event.id),
            description=f"{d['event_type']} event on lot via WhatsApp",
        )

        from apps.blockchain.tasks import anchor_event_hash
        anchor_event_hash.delay(str(event.id))

        end_conversation(conv)
        return Reply(
            f"Event '{d['event_type']}' recorded and queued for blockchain anchoring.\n"
            f"Event ID: {str(event.id)[:8]}...",
            end_conversation=True,
        )
