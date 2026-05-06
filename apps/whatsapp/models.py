from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.common.enums import (
    ConversationType,
    WhatsAppDeliveryStatus,
    WhatsAppDirection,
)
from apps.common.models import BaseModel


class WhatsAppContact(BaseModel):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="whatsapp_contact",
    )
    phone_number = models.CharField(max_length=20, unique=True, db_index=True)
    display_name = models.CharField(max_length=200, blank=True, default="")
    preferred_language = models.CharField(max_length=10, default="en")
    is_verified = models.BooleanField(default=False)
    linked_role = models.CharField(max_length=30, blank=True, default="")
    consent_given = models.BooleanField(default=False)
    consent_given_at = models.DateTimeField(null=True, blank=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "whatsapp_contact"
        ordering = ["-last_seen_at"]

    def __str__(self):
        name = self.display_name or self.phone_number
        return f"{name} ({'linked' if self.user else 'unlinked'})"


class WhatsAppConversation(BaseModel):
    contact = models.ForeignKey(
        WhatsAppContact,
        on_delete=models.CASCADE,
        related_name="conversations",
    )
    conversation_type = models.CharField(
        max_length=30,
        choices=ConversationType.choices,
        default=ConversationType.GENERAL,
    )
    current_state = models.CharField(max_length=100, default="INIT")
    current_intent = models.CharField(max_length=100, blank=True, default="")
    is_active = models.BooleanField(default=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    state_data = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "whatsapp_conversation"
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["contact", "is_active"]),
        ]

    def __str__(self):
        return f"{self.conversation_type}:{self.current_state} ({self.contact})"

    @property
    def is_expired(self):
        if self.expires_at and timezone.now() > self.expires_at:
            return True
        return False


class WhatsAppMessageLog(BaseModel):
    conversation = models.ForeignKey(
        WhatsAppConversation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="messages",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="whatsapp_messages",
    )
    phone_number = models.CharField(max_length=20, db_index=True)
    direction = models.CharField(max_length=10, choices=WhatsAppDirection.choices)
    message_type = models.CharField(max_length=50, blank=True, default="text")
    message_body = models.TextField(blank=True, default="")
    media_url = models.URLField(blank=True, default="")
    media_type = models.CharField(max_length=50, blank=True, default="")
    provider_message_id = models.CharField(max_length=100, blank=True, default="", db_index=True)
    delivery_status = models.CharField(
        max_length=20,
        choices=WhatsAppDeliveryStatus.choices,
        default=WhatsAppDeliveryStatus.QUEUED,
    )
    error_message = models.TextField(blank=True, default="")
    raw_payload = models.JSONField(default=dict, blank=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "whatsapp_message_log"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["phone_number", "direction"]),
        ]

    def __str__(self):
        return f"[{self.direction}] {self.phone_number}: {self.message_body[:50]}"


class WhatsAppIntentLog(BaseModel):
    conversation = models.ForeignKey(
        WhatsAppConversation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="intent_logs",
    )
    detected_intent = models.CharField(max_length=100)
    confidence = models.FloatField(default=1.0)
    routed_handler = models.CharField(max_length=200, blank=True, default="")
    ai_used = models.BooleanField(default=False)
    raw_input = models.TextField(blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "whatsapp_intent_log"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Intent: {self.detected_intent} (conf={self.confidence})"


class WhatsAppTemplateLog(BaseModel):
    template_name = models.CharField(max_length=100, db_index=True)
    contact = models.ForeignKey(
        WhatsAppContact,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="template_logs",
    )
    related_object_type = models.CharField(max_length=50, blank=True, default="")
    related_object_id = models.UUIDField(null=True, blank=True)
    send_status = models.CharField(
        max_length=20,
        choices=WhatsAppDeliveryStatus.choices,
        default=WhatsAppDeliveryStatus.QUEUED,
    )
    provider_response = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "whatsapp_template_log"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Template: {self.template_name} -> {self.contact}"
