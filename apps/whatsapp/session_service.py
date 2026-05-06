"""
Session service for managing WhatsApp contacts and conversations.
Handles contact resolution, conversation lifecycle, and state persistence.
"""
import logging
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.common.enums import ConversationType
from apps.common.utils import normalize_phone_number
from apps.whatsapp.models import WhatsAppContact, WhatsAppConversation

User = get_user_model()
logger = logging.getLogger(__name__)

CONVERSATION_TTL_MINUTES = getattr(settings, "WHATSAPP_CONVERSATION_TTL_MINUTES", 30)


def get_or_create_contact(phone: str) -> WhatsAppContact:
    normalized = normalize_phone_number(phone) or phone
    contact, created = WhatsAppContact.objects.get_or_create(
        phone_number=normalized,
        defaults={"display_name": normalized},
    )
    if not contact.user:
        user = User.objects.filter(phone_number=normalized, is_active=True).first()
        if user:
            contact.user = user
            contact.linked_role = user.role
            contact.is_verified = True
            contact.display_name = user.full_name
            contact.save(update_fields=[
                "user", "linked_role", "is_verified", "display_name", "updated_at",
            ])
    contact.last_seen_at = timezone.now()
    contact.save(update_fields=["last_seen_at"])
    return contact


def get_active_conversation(contact: WhatsAppContact) -> WhatsAppConversation | None:
    conv = WhatsAppConversation.objects.filter(
        contact=contact, is_active=True,
    ).order_by("-updated_at").first()

    if conv and conv.is_expired:
        conv.is_active = False
        conv.save(update_fields=["is_active", "updated_at"])
        return None

    return conv


def start_conversation(
    contact: WhatsAppContact,
    conversation_type: str = ConversationType.GENERAL,
    initial_state: str = "INIT",
) -> WhatsAppConversation:
    WhatsAppConversation.objects.filter(
        contact=contact, is_active=True,
    ).update(is_active=False)

    conv = WhatsAppConversation.objects.create(
        contact=contact,
        conversation_type=conversation_type,
        current_state=initial_state,
        is_active=True,
        expires_at=timezone.now() + timedelta(minutes=CONVERSATION_TTL_MINUTES),
        state_data={},
    )
    return conv


def advance_state(conv: WhatsAppConversation, new_state: str, data_updates: dict | None = None):
    conv.current_state = new_state
    if data_updates:
        conv.state_data.update(data_updates)
    conv.expires_at = timezone.now() + timedelta(minutes=CONVERSATION_TTL_MINUTES)
    conv.save(update_fields=["current_state", "state_data", "expires_at", "updated_at"])


def end_conversation(conv: WhatsAppConversation):
    conv.is_active = False
    conv.save(update_fields=["is_active", "updated_at"])


def reset_conversation(contact: WhatsAppContact):
    WhatsAppConversation.objects.filter(
        contact=contact, is_active=True,
    ).update(is_active=False)
