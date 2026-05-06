"""
Document upload workflow via WhatsApp.

Handles both:
1. Guided upload (user types UPLOAD DOCUMENT, then sends media)
2. Unsolicited media (user sends image/document without context)

States:
  INIT -> ASK_DOC_TYPE -> ASK_LOT_LINK -> AWAITING_MEDIA -> CONFIRM -> DONE
  or
  MEDIA_RECEIVED -> ASK_DOC_TYPE -> ASK_LOT_LINK -> CONFIRM -> DONE
"""
import logging

from apps.common.enums import DocumentType
from apps.whatsapp.session_service import advance_state, end_conversation
from apps.whatsapp.workflows.base import BaseWorkflow, Reply

logger = logging.getLogger(__name__)

DOC_TYPE_OPTIONS = [
    (DocumentType.RECEIPT, "Receipt"),
    (DocumentType.CERTIFICATE, "Certificate"),
    (DocumentType.GRADING_SHEET, "Grading Sheet"),
    (DocumentType.DELIVERY_NOTE, "Delivery Note"),
    (DocumentType.INSPECTION_RECORD, "Inspection Record"),
    (DocumentType.PROOF_OF_PAYMENT, "Proof of Payment"),
    (DocumentType.DISPUTE_EVIDENCE, "Dispute Evidence"),
    (DocumentType.OTHER, "Other"),
]


class DocumentUploadWorkflow(BaseWorkflow):

    def get_name(self) -> str:
        return "document_upload"

    def handle_init(self, conv, body, contact):
        if not contact.user:
            end_conversation(conv)
            return Reply("You must be registered first. Type REGISTER.", end_conversation=True)

        advance_state(conv, "ASK_DOC_TYPE")
        lines = ["What type of document?\n"]
        for i, (_, label) in enumerate(DOC_TYPE_OPTIONS, 1):
            lines.append(f"{i}. {label}")
        lines.append("\nChoose a number:")
        return Reply("\n".join(lines))

    def handle_media_received(self, conv, body, contact):
        advance_state(conv, "ASK_DOC_TYPE")
        lines = ["Got your file! What type of document is it?\n"]
        for i, (_, label) in enumerate(DOC_TYPE_OPTIONS, 1):
            lines.append(f"{i}. {label}")
        return Reply("\n".join(lines))

    def handle_ask_doc_type(self, conv, body, contact):
        choice = self._parse_choice(body, len(DOC_TYPE_OPTIONS))
        if not choice:
            return Reply(f"Please enter a number between 1 and {len(DOC_TYPE_OPTIONS)}:")

        doc_type = DOC_TYPE_OPTIONS[choice - 1][0]
        advance_state(conv, "ASK_LOT_LINK", {"doc_type": doc_type})

        from apps.lots.models import Lot
        lots = list(
            Lot.objects.filter(farm__owner=contact.user)
            .order_by("-created_at")[:10]
        )
        if not lots:
            advance_state(conv, "AWAITING_MEDIA" if not conv.state_data.get("media_url") else "CONFIRM")
            if conv.state_data.get("media_url"):
                return self._show_confirm(conv)
            return Reply("No lots found to link. Send your document/photo now:")

        lot_list = ["Link this document to a lot (or type SKIP):\n"]
        lot_ids = []
        for i, lot in enumerate(lots, 1):
            lot_list.append(f"{i}. {lot.lot_number}")
            lot_ids.append(str(lot.id))

        advance_state(conv, "ASK_LOT_LINK", {"lot_ids": lot_ids})
        return Reply("\n".join(lot_list))

    def handle_ask_lot_link(self, conv, body, contact):
        if body.strip().lower() == "skip":
            advance_state(conv, "AWAITING_MEDIA" if not conv.state_data.get("media_url") else "CONFIRM")
            if conv.state_data.get("media_url"):
                return self._show_confirm(conv)
            return Reply("Send your document or photo now:")

        lot_ids = conv.state_data.get("lot_ids", [])
        choice = self._parse_choice(body, len(lot_ids)) if lot_ids else None
        if choice:
            advance_state(conv, "AWAITING_MEDIA" if not conv.state_data.get("media_url") else "CONFIRM", {
                "lot_id": lot_ids[choice - 1],
            })
        else:
            advance_state(conv, "AWAITING_MEDIA" if not conv.state_data.get("media_url") else "CONFIRM")

        if conv.state_data.get("media_url"):
            return self._show_confirm(conv)
        return Reply("Send your document or photo now:")

    def handle_awaiting_media(self, conv, body, contact):
        media_url = conv.state_data.get("media_url")
        if not media_url:
            return Reply(
                "Please send a photo or document. If you don't have one now, type CANCEL."
            )
        advance_state(conv, "CONFIRM")
        return self._show_confirm(conv)

    def _show_confirm(self, conv) -> Reply:
        d = conv.state_data
        doc_label = d.get("doc_type", "OTHER")
        for code, label in DOC_TYPE_OPTIONS:
            if code == doc_label:
                doc_label = label
                break
        return Reply(
            "Confirm document upload:\n\n"
            f"Type: {doc_label}\n"
            f"Lot: {d.get('lot_id', 'None')[:8] if d.get('lot_id') else 'Not linked'}\n"
            f"Media: {'Attached' if d.get('media_url') else 'Pending'}\n\n"
            "Reply YES to submit or NO to cancel."
        )

    def handle_confirm(self, conv, body, contact):
        if body.strip().lower() not in ("yes", "y"):
            end_conversation(conv)
            return Reply("Upload cancelled.", end_conversation=True)

        d = conv.state_data
        media_url = d.get("media_url")
        if not media_url:
            end_conversation(conv)
            return Reply("No media was attached. Upload cancelled.", end_conversation=True)

        from apps.whatsapp.tasks import process_whatsapp_media_task
        process_whatsapp_media_task.delay(
            media_url=media_url,
            media_type=d.get("media_type", ""),
            user_id=str(contact.user.id),
            doc_type=d.get("doc_type", DocumentType.OTHER),
            lot_id=d.get("lot_id"),
            phone=contact.phone_number,
        )

        end_conversation(conv)
        return Reply(
            "Document submitted for processing.\n"
            "You'll receive a confirmation once it's hashed and stored.",
            end_conversation=True,
        )
