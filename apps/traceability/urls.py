from django.urls import path

from apps.traceability.views import TraceEventDetailView, TraceEventListCreateView

urlpatterns = [
    path("", TraceEventListCreateView.as_view(), name="trace-event-list"),
    path("<uuid:pk>/", TraceEventDetailView.as_view(), name="trace-event-detail"),
]
