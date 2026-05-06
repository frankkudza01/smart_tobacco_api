from django.urls import path

from apps.worldready.views import (
    AnalyticsUxTasksExportView,
    GuidedFormsSchemaView,
    I18nStringsView,
    SusSurveyResponseView,
    SusSurveySendHookView,
    UserPreferenceMeView,
)

urlpatterns = [
    path("preferences/me/", UserPreferenceMeView.as_view(), name="preferences-me"),
    path("i18n/strings/", I18nStringsView.as_view(), name="i18n-strings"),
    path("ux/guided-forms/", GuidedFormsSchemaView.as_view(), name="ux-guided-forms"),
    path("analytics/ux/tasks/", AnalyticsUxTasksExportView.as_view(), name="analytics-ux-tasks"),
    path("surveys/sus/send/", SusSurveySendHookView.as_view(), name="surveys-sus-send"),
    path("surveys/sus/response/", SusSurveyResponseView.as_view(), name="surveys-sus-response"),
]
