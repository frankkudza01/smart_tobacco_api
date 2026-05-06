from django.urls import path

from apps.privacy_controls.views import PrivacyErasureRequestView, PrivacyExportMeView

urlpatterns = [
    path("privacy/me/export/", PrivacyExportMeView.as_view(), name="privacy-export-me"),
    path("privacy/me/erasure/", PrivacyErasureRequestView.as_view(), name="privacy-erasure-request"),
]
