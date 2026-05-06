from django.urls import path

from apps.common.views import HealthCheckView, ReadinessCheckView, LivenessCheckView

urlpatterns = [
    path("health/", HealthCheckView.as_view(), name="health-check"),
    path("readiness/", ReadinessCheckView.as_view(), name="readiness-check"),
    path("liveness/", LivenessCheckView.as_view(), name="liveness-check"),
]
