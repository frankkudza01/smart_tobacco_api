from __future__ import annotations

from django.conf import settings
from django.db import models

from apps.common.enums import LiteracyMode, PreferredLanguageCode, UXChannel
from apps.common.models import BaseModel
from apps.organizations.models import Organization


class UserPreference(BaseModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="ux_preferences",
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="user_preferences",
        db_index=True,
    )
    preferred_language = models.CharField(
        max_length=8,
        choices=PreferredLanguageCode.choices,
        default=PreferredLanguageCode.EN,
    )
    literacy_mode = models.CharField(
        max_length=16,
        choices=LiteracyMode.choices,
        default=LiteracyMode.NORMAL,
    )
    voice_mode_enabled = models.BooleanField(default=False)

    class Meta:
        db_table = "worldready_user_preference"
        unique_together = [["user", "organization"]]
        indexes = [models.Index(fields=["organization", "user"])]


class TranslationOverride(BaseModel):
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="translation_overrides",
        db_index=True,
    )
    key = models.CharField(max_length=200, db_index=True)
    locale = models.CharField(max_length=16, db_index=True)
    value = models.TextField()

    class Meta:
        db_table = "worldready_translation_override"
        unique_together = [["organization", "key", "locale"]]


class TaskCompletionLog(BaseModel):
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="task_completion_logs",
        db_index=True,
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="task_completion_logs",
    )
    channel = models.CharField(max_length=20, choices=UXChannel.choices, db_index=True)
    task_name = models.CharField(max_length=120, db_index=True)
    started_at = models.DateTimeField(db_index=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    success = models.BooleanField(default=False)
    error_code = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        db_table = "worldready_task_completion_log"
        ordering = ["-started_at"]
        indexes = [models.Index(fields=["organization", "channel", "task_name"])]


class SupportRequestLog(BaseModel):
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="support_request_logs",
        db_index=True,
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="support_request_logs",
    )
    channel = models.CharField(max_length=20, choices=UXChannel.choices, db_index=True)
    request_type = models.CharField(max_length=64, db_index=True)
    body_preview = models.CharField(max_length=240, blank=True, default="")

    class Meta:
        db_table = "worldready_support_request_log"
        ordering = ["-created_at"]


class SusSurveyResponse(BaseModel):
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="sus_survey_responses",
        db_index=True,
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sus_survey_responses",
    )
    channel = models.CharField(max_length=20, choices=UXChannel.choices, blank=True, default="")
    scores_json = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "worldready_sus_survey_response"
        ordering = ["-created_at"]
