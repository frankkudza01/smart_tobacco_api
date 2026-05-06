from django.conf import settings
from django.db import models

from apps.common.models import BaseModel


class AIInteractionLog(BaseModel):
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="ai_interactions",
    )
    prompt = models.TextField()
    tools_used = models.JSONField(default=list, blank=True)
    result = models.TextField(blank=True, default="")
    model_name = models.CharField(max_length=100, blank=True, default="")
    tokens_used = models.PositiveIntegerField(default=0)
    duration_ms = models.PositiveIntegerField(default=0)
    correlation_id = models.CharField(max_length=100, blank=True, default="")
    is_error = models.BooleanField(default=False)
    error_detail = models.TextField(blank=True, default="")

    class Meta:
        db_table = "ai_assistant_interaction_log"
        ordering = ["-created_at"]

    def __str__(self):
        return f"AI query by {self.actor} at {self.created_at}"
