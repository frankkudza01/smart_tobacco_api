from django.urls import path

from .views import FarmerAdvisorTelemetryView

urlpatterns = [
    path("farmer-advisor/telemetry/", FarmerAdvisorTelemetryView.as_view(), name="farmer-advisor-telemetry"),
]
