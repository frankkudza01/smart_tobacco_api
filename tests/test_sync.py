import uuid
import pytest
from django.urls import reverse
from rest_framework import status

from apps.common.enums import SyncStatus
from apps.sync.models import SyncRecord


@pytest.mark.django_db
class TestBatchSync:
    def test_sync_farm_record(self, authenticated_farmer_client):
        url = reverse("batch-sync")
        farm_id = str(uuid.uuid4())
        data = {
            "records": [
                {
                    "client_record_id": farm_id,
                    "idempotency_key": f"farm-{farm_id}",
                    "payload_type": "farm",
                    "payload": {
                        "id": farm_id,
                        "name": "Offline Farm",
                        "district": "Mvurwi",
                        "province": "Mashonaland Central",
                    },
                }
            ]
        }
        response = authenticated_farmer_client.post(url, data, format="json")
        assert response.status_code == status.HTTP_200_OK
        results = response.data["results"]
        assert len(results) == 1
        assert results[0]["status"] == SyncStatus.SYNCED

    def test_idempotency_duplicate_ignored(self, authenticated_farmer_client):
        url = reverse("batch-sync")
        farm_id = str(uuid.uuid4())
        idem_key = f"farm-{farm_id}"
        record = {
            "client_record_id": farm_id,
            "idempotency_key": idem_key,
            "payload_type": "farm",
            "payload": {"id": farm_id, "name": "Dup Farm", "district": "Test"},
        }

        resp1 = authenticated_farmer_client.post(url, {"records": [record]}, format="json")
        assert resp1.data["results"][0]["status"] == SyncStatus.SYNCED

        resp2 = authenticated_farmer_client.post(url, {"records": [record]}, format="json")
        assert resp2.data["results"][0]["status"] == SyncStatus.DUPLICATE_IGNORED

    def test_sync_invalid_payload_type(self, authenticated_farmer_client):
        url = reverse("batch-sync")
        data = {
            "records": [
                {
                    "client_record_id": str(uuid.uuid4()),
                    "idempotency_key": "bad-type-key",
                    "payload_type": "unknown_type",
                    "payload": {},
                }
            ]
        }
        response = authenticated_farmer_client.post(url, data, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data.get("success") is False
        assert response.data.get("errors")

    def test_events_batch_rejects_non_trace(self, authenticated_farmer_client):
        url = reverse("sync-events-batch")
        farm_id = str(uuid.uuid4())
        data = {
            "records": [
                {
                    "client_record_id": str(uuid.uuid4()),
                    "idempotency_key": "farm-only",
                    "payload_type": "farm",
                    "payload": {"id": farm_id, "name": "X", "district": "Y"},
                }
            ]
        }
        response = authenticated_farmer_client.post(url, data, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
