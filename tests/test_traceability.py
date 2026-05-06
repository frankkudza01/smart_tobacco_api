import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework import status

from apps.common.enums import TraceEventType
from apps.traceability.models import TraceEvent


@pytest.mark.django_db
class TestTraceEvents:
    def test_create_trace_event(self, authenticated_farmer_client, lot):
        url = reverse("trace-event-list")
        data = {
            "lot": str(lot.id),
            "event_type": TraceEventType.PLANTING,
            "timestamp": timezone.now().isoformat(),
            "location": "Field A",
            "payload": {"seed_variety": "KRK26"},
        }
        response = authenticated_farmer_client.post(url, data, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["event_type"] == TraceEventType.PLANTING
        assert response.data["event_hash"] != ""

    def test_trace_event_hash_computed(self, authenticated_farmer_client, lot):
        url = reverse("trace-event-list")
        data = {
            "lot": str(lot.id),
            "event_type": TraceEventType.HARVESTING,
            "timestamp": timezone.now().isoformat(),
        }
        response = authenticated_farmer_client.post(url, data, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        event = TraceEvent.objects.get(id=response.data["id"])
        assert len(event.event_hash) == 64

    def test_list_trace_events(self, authenticated_farmer_client, lot):
        from tests.factories import TraceEventFactory
        TraceEventFactory(lot=lot, actor=lot.farm.owner)
        TraceEventFactory(lot=lot, actor=lot.farm.owner, event_type=TraceEventType.HARVESTING)

        url = reverse("trace-event-list")
        response = authenticated_farmer_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 2
