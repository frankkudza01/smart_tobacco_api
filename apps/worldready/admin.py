from django.contrib import admin

from apps.worldready.models import (
    SupportRequestLog,
    SusSurveyResponse,
    TaskCompletionLog,
    TranslationOverride,
    UserPreference,
)


@admin.register(UserPreference)
class UserPreferenceAdmin(admin.ModelAdmin):
    list_display = ("user", "organization", "preferred_language", "literacy_mode")


@admin.register(TranslationOverride)
class TranslationOverrideAdmin(admin.ModelAdmin):
    list_display = ("organization", "key", "locale")


@admin.register(TaskCompletionLog)
class TaskCompletionLogAdmin(admin.ModelAdmin):
    list_display = ("organization", "task_name", "channel", "success", "started_at")


@admin.register(SupportRequestLog)
class SupportRequestLogAdmin(admin.ModelAdmin):
    list_display = ("organization", "request_type", "channel", "created_at")


@admin.register(SusSurveyResponse)
class SusSurveyResponseAdmin(admin.ModelAdmin):
    list_display = ("organization", "user", "created_at")
