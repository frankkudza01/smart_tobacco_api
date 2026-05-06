import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework import status

from apps.common.enums import TraceEventType, UserRole
from apps.organizations.models import OrganizationMembership
from apps.provenance.services import get_lot_provenance
from apps.traceability.models import TraceEvent


@pytest.mark.django_db
class TestProvenance:
    def test_lot_provenance_service(self, lot):
        farmer = lot.farm.owner
        TraceEvent.objects.create(
            lot=lot, actor=farmer,
            event_type=TraceEventType.PLANTING,
            timestamp=timezone.now(),
        )
        TraceEvent.objects.create(
            lot=lot, actor=farmer,
            event_type=TraceEventType.HARVESTING,
            timestamp=timezone.now(),
        )

        result = get_lot_provenance(lot.id, queried_by=farmer)
        assert result is not None
        assert result["lot"]["lot_number"] == lot.lot_number
        assert len(result["timeline"]) == 2

    def test_lot_provenance_endpoint(self, authenticated_farmer_client, lot):
        url = reverse("lot-provenance", kwargs={"lot_id": lot.id})
        response = authenticated_farmer_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert "lot" in response.data
        assert "timeline" in response.data
        assert "documents" in response.data

    def test_provenance_not_found(self, authenticated_farmer_client):
        import uuid
        url = reverse("lot-provenance", kwargs={"lot_id": uuid.uuid4()})
        response = authenticated_farmer_client.get(url)
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_farmer_can_post_farm_provenance_checks_own_org_farm(
        self, authenticated_farmer_client, farmer_user, farm, organization
    ):
        farm.organization = organization
        farm.save(update_fields=["organization"])
        OrganizationMembership.objects.update_or_create(
            user=farmer_user,
            organization=organization,
            defaults={
                "role": UserRole.SMALLHOLDER_FARMER,
                "is_primary": True,
                "is_active": True,
            },
        )
        url = reverse("farm-provenance-checks-run", kwargs={"farm_id": farm.id})
        response = authenticated_farmer_client.post(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data.get("ok") is True
        assert "lots_accessible" in response.data
