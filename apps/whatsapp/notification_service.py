"""
Outbound WhatsApp notification service.
Sends proactive notifications for business events.
All notifications are audited and logged via WhatsAppTemplateLog.
"""
import logging

from apps.whatsapp.tasks import send_template_notification_task

logger = logging.getLogger(__name__)


def notify_farm_registered(user, farm):
    if not user.phone_number:
        return
    send_template_notification_task.delay(
        phone=user.phone_number,
        template_name="farm_registered",
        body=(
            f"Your farm '{farm.name}' has been registered successfully!\n"
            f"Farm ID: {str(farm.id)[:8]}...\n"
            "Type CREATE LOT to add lots."
        ),
        user_id=str(user.id),
        related_object_type="Farm",
        related_object_id=str(farm.id),
    )


def notify_season_created(user, season, farm=None):
    if not user.phone_number:
        return
    farm_label = farm.name if farm is not None else "your farm"
    send_template_notification_task.delay(
        phone=user.phone_number,
        template_name="season_created",
        body=(
            f"Season {season.crop_year} is active for farm '{farm_label}'.\n"
            "Type CREATE LOT to add lots to this season."
        ),
        user_id=str(user.id),
        related_object_type="Season",
        related_object_id=str(season.id),
    )


def notify_event_submitted(user, trace_event):
    if not user.phone_number:
        return
    send_template_notification_task.delay(
        phone=user.phone_number,
        template_name="event_submitted",
        body=(
            f"Event '{trace_event.event_type}' recorded for lot "
            f"{trace_event.lot.lot_number}.\n"
            f"Blockchain anchoring: {trace_event.anchor_status}"
        ),
        user_id=str(user.id),
        related_object_type="TraceEvent",
        related_object_id=str(trace_event.id),
    )


def notify_document_anchored(user, document):
    if not user.phone_number:
        return
    send_template_notification_task.delay(
        phone=user.phone_number,
        template_name="document_anchored",
        body=(
            f"Document '{document.title}' has been anchored to the blockchain!\n"
            f"Hash: {document.sha256_hash[:16]}...\n"
            f"Status: {document.anchor_status}"
        ),
        user_id=str(user.id),
        related_object_type="Document",
        related_object_id=str(document.id),
    )


def notify_settlement_created(farmer, settlement):
    if not farmer or not farmer.phone_number:
        return
    lot_num = settlement.sale.lot.lot_number if settlement.sale and settlement.sale.lot else "N/A"
    send_template_notification_task.delay(
        phone=farmer.phone_number,
        template_name="settlement_created",
        body=(
            f"A settlement has been created for your lot {lot_num}.\n"
            f"Amount: ${settlement.amount_due} {settlement.currency}\n"
            f"Status: {settlement.status}\n"
            "Type MY SETTLEMENTS for details."
        ),
        user_id=str(farmer.id),
        related_object_type="Settlement",
        related_object_id=str(settlement.id),
    )


def notify_payment_status_changed(farmer, settlement, old_status):
    if not farmer or not farmer.phone_number:
        return
    lot_num = settlement.sale.lot.lot_number if settlement.sale and settlement.sale.lot else "N/A"
    send_template_notification_task.delay(
        phone=farmer.phone_number,
        template_name="payment_status_changed",
        body=(
            f"Payment update for lot {lot_num}:\n"
            f"Status: {old_status} → {settlement.status}\n"
            f"Amount: ${settlement.amount_paid} of ${settlement.amount_due}\n"
            "Type MY SETTLEMENTS for details."
        ),
        user_id=str(farmer.id),
        related_object_type="Settlement",
        related_object_id=str(settlement.id),
    )


def notify_dispute_opened(user, dispute):
    if not user.phone_number:
        return
    send_template_notification_task.delay(
        phone=user.phone_number,
        template_name="dispute_opened",
        body=(
            f"Dispute '{dispute.title}' has been opened.\n"
            f"ID: {str(dispute.id)[:8]}...\n"
            f"Status: {dispute.status}\n"
            "You'll be notified when there's an update."
        ),
        user_id=str(user.id),
        related_object_type="Dispute",
        related_object_id=str(dispute.id),
    )


def notify_dispute_updated(user, dispute):
    if not user.phone_number:
        return
    send_template_notification_task.delay(
        phone=user.phone_number,
        template_name="dispute_updated",
        body=(
            f"Dispute '{dispute.title}' has been updated.\n"
            f"Status: {dispute.status}\n"
            f"Resolution: {dispute.resolution[:100] if dispute.resolution else 'Pending'}"
        ),
        user_id=str(user.id),
        related_object_type="Dispute",
        related_object_id=str(dispute.id),
    )


def notify_dispute_resolved(user, dispute):
    if not user.phone_number:
        return
    send_template_notification_task.delay(
        phone=user.phone_number,
        template_name="dispute_resolved",
        body=(
            f"Your dispute '{dispute.title}' has been resolved!\n"
            f"Resolution: {dispute.resolution[:150] if dispute.resolution else 'See details in app.'}"
        ),
        user_id=str(user.id),
        related_object_type="Dispute",
        related_object_id=str(dispute.id),
    )


def notify_grading_complete(farmer, grade_record):
    if not farmer or not farmer.phone_number:
        return
    send_template_notification_task.delay(
        phone=farmer.phone_number,
        template_name="grading_complete",
        body=(
            f"Your lot {grade_record.lot.lot_number} has been graded!\n"
            f"Grade: {grade_record.grade}\n"
            f"Weight: {grade_record.weight_kg} kg\n"
            "The lot is now ready for sale."
        ),
        user_id=str(farmer.id),
        related_object_type="GradeRecord",
        related_object_id=str(grade_record.id),
    )


def notify_sale_recorded(farmer, sale):
    if not farmer or not farmer.phone_number:
        return
    send_template_notification_task.delay(
        phone=farmer.phone_number,
        template_name="sale_recorded",
        body=(
            f"Your lot {sale.lot.lot_number} has been sold!\n"
            f"Amount: ${sale.total_amount} {sale.currency}\n"
            "A settlement will be created shortly."
        ),
        user_id=str(farmer.id),
        related_object_type="Sale",
        related_object_id=str(sale.id),
    )


def notify_buyer_pending_dispute(buyer, dispute):
    if not buyer or not buyer.phone_number:
        return
    send_template_notification_task.delay(
        phone=buyer.phone_number,
        template_name="buyer_pending_dispute",
        body=(
            f"A new dispute requires your attention:\n"
            f"'{dispute.title}'\n"
            f"Status: {dispute.status}\n"
            "Type RESPOND DISPUTE to review."
        ),
        user_id=str(buyer.id),
        related_object_type="Dispute",
        related_object_id=str(dispute.id),
    )


def notify_provenance_verified(user, lot, verification_result: str):
    if not user.phone_number:
        return
    send_template_notification_task.delay(
        phone=user.phone_number,
        template_name="provenance_verified",
        body=(
            f"Provenance verification for lot {lot.lot_number}:\n"
            f"Result: {verification_result}"
        ),
        user_id=str(user.id),
        related_object_type="Lot",
        related_object_id=str(lot.id),
    )


def notify_reminder(user, message: str, template_name: str = "generic_reminder"):
    if not user.phone_number:
        return
    send_template_notification_task.delay(
        phone=user.phone_number,
        template_name=template_name,
        body=message,
        user_id=str(user.id),
    )
