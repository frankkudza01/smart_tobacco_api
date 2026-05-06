import pytest
from django.urls import reverse
from rest_framework import status


@pytest.mark.django_db
class TestRolePermissions:
    """Verify RBAC enforcement across critical endpoints."""

    def test_farmer_cannot_access_admin_user_list(self, authenticated_farmer_client):
        resp = authenticated_farmer_client.get(reverse("user-list"))
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_buyer_cannot_create_farm(self, authenticated_buyer_client):
        resp = authenticated_buyer_client.post(reverse("farm-list"), {
            "name": "Buyer Farm", "district": "Test"
        })
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_farmer_cannot_create_grading(self, authenticated_farmer_client, lot):
        resp = authenticated_farmer_client.post(reverse("grading-list"), {
            "lot": str(lot.id), "grade": "C1L",
            "weight_kg": "500", "graded_at": "2025-01-01T00:00:00Z",
        })
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_farmer_cannot_create_sale(self, authenticated_farmer_client, lot):
        resp = authenticated_farmer_client.post(reverse("sale-list"), {
            "lot": str(lot.id), "sale_type": "AUCTION",
            "price_per_kg": "4.0", "total_weight_kg": "500",
            "total_amount": "2000", "sale_date": "2025-01-01T00:00:00Z",
        })
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_unauthenticated_cannot_access_lots(self, api_client):
        resp = api_client.get(reverse("lot-list"))
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    def test_auditor_can_read_provenance(self, authenticated_auditor_client, lot):
        url = reverse("lot-provenance", kwargs={"lot_id": lot.id})
        resp = authenticated_auditor_client.get(url)
        assert resp.status_code == status.HTTP_200_OK

    def test_health_endpoint_is_public(self, api_client):
        resp = api_client.get(reverse("health-check"))
        assert resp.status_code == status.HTTP_200_OK
