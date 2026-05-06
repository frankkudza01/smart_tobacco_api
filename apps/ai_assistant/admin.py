from django.contrib import admin

from apps.ai_assistant.models import AIInteractionLog


@admin.register(AIInteractionLog)
class AIInteractionLogAdmin(admin.ModelAdmin):
    list_display = ("actor", "model_name", "is_error", "duration_ms", "created_at")
    list_filter = ("is_error", "model_name")
    search_fields = ("actor__email", "prompt")
    raw_id_fields = ("actor",)
    readonly_fields = ("prompt", "result", "tools_used", "correlation_id")
