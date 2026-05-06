from django.contrib import admin

from apps.whatsapp.models import (
    WhatsAppContact,
    WhatsAppConversation,
    WhatsAppIntentLog,
    WhatsAppMessageLog,
    WhatsAppTemplateLog,
)


@admin.register(WhatsAppContact)
class WhatsAppContactAdmin(admin.ModelAdmin):
    list_display = (
        "phone_number", "display_name", "linked_role", "is_verified",
        "consent_given", "last_seen_at",
    )
    list_filter = ("is_verified", "linked_role", "consent_given")
    search_fields = ("phone_number", "display_name")
    raw_id_fields = ("user",)
    readonly_fields = ("phone_number",)


@admin.register(WhatsAppConversation)
class WhatsAppConversationAdmin(admin.ModelAdmin):
    list_display = (
        "contact", "conversation_type", "current_state", "is_active",
        "created_at", "expires_at",
    )
    list_filter = ("conversation_type", "is_active", "current_state")
    search_fields = ("contact__phone_number",)
    raw_id_fields = ("contact",)
    readonly_fields = ("state_data",)


@admin.register(WhatsAppMessageLog)
class WhatsAppMessageLogAdmin(admin.ModelAdmin):
    list_display = (
        "phone_number", "direction", "message_type", "delivery_status",
        "provider_message_id", "created_at",
    )
    list_filter = ("direction", "delivery_status", "message_type")
    search_fields = ("phone_number", "message_body", "provider_message_id")
    raw_id_fields = ("user", "conversation")
    readonly_fields = ("provider_message_id", "message_body", "raw_payload", "media_url")


@admin.register(WhatsAppIntentLog)
class WhatsAppIntentLogAdmin(admin.ModelAdmin):
    list_display = (
        "detected_intent", "confidence", "routed_handler", "ai_used", "created_at",
    )
    list_filter = ("ai_used", "detected_intent")
    search_fields = ("detected_intent", "routed_handler")
    raw_id_fields = ("conversation",)
    readonly_fields = ("metadata",)


@admin.register(WhatsAppTemplateLog)
class WhatsAppTemplateLogAdmin(admin.ModelAdmin):
    list_display = (
        "template_name", "contact", "related_object_type", "send_status", "created_at",
    )
    list_filter = ("template_name", "send_status")
    search_fields = ("template_name",)
    raw_id_fields = ("contact",)
    readonly_fields = ("provider_response",)
