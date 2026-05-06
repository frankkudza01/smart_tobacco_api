"""
Smoke tests for BUYER_CONTRACTOR API paths (matches typical app "buyer" screens).
Requires PostgreSQL test DB (config.settings.test).
"""
import pytest
from django.urls import reverse
from rest_framework import status

from apps.common.enums import TraceEventType, UserRole
from apps.organizations.models import OrganizationMembership
from django.utils import timezone

from tests.factories import (
    BuyerFactory,
    FarmFactory,
    FarmerFactory,
    LotFactory,
    OrganizationFactory,
    SeasonFactory,
)


@pytest.fixture
def buyer_with_shared_tenant(db):
    """Buyer + farmer in same org; farm linked so buyer can list lots."""
    org = OrganizationFactory()
    buyer = BuyerFactory(link_organization=org)
    farmer = FarmerFactory()
    OrganizationMembership.objects.get_or_create(
        user=farmer,
        organization=org,
        defaults={
            "role": UserRole.SMALLHOLDER_FARMER,
            "is_primary": True,
            "is_active": True,
        },
    )
    farm = FarmFactory(owner=farmer, organization=org)
    season = SeasonFactory(farm=farm)
    lot = LotFactory(season=season, farm=farm)
    return buyer, lot


@pytest.mark.django_db
class TestBuyerRegistrationOrg:
    def test_new_buyer_gets_organization(self, db):
        from apps.accounts.services import register_user
        from apps.common.org_utils import get_user_primary_organization

        u = register_user(
            email="newbuyer@test.com",
            password="secret12345",
            first_name="New",
            last_name="Buyer",
            role=UserRole.BUYER_CONTRACTOR,
        )
        org = get_user_primary_organization(u)
        assert org is not None
        assert "Buyer" in org.name


@pytest.mark.django_db
class TestBuyerAuthenticatedEndpoints:
    def test_preferences_me_ok(self, api_client, buyer_with_shared_tenant):
        buyer, _lot = buyer_with_shared_tenant
        api_client.force_authenticate(user=buyer)
        r = api_client.get(reverse("preferences-me"))
        assert r.status_code == status.HTTP_200_OK

    def test_i18n_and_guided_forms_ok(self, api_client, buyer_with_shared_tenant):
        buyer, _lot = buyer_with_shared_tenant
        api_client.force_authenticate(user=buyer)
        assert api_client.get(reverse("i18n-strings")).status_code == status.HTTP_200_OK
        assert api_client.get(reverse("ux-guided-forms")).status_code == status.HTTP_200_OK

    def test_forecasts_and_anomalies_list_ok(self, api_client, buyer_with_shared_tenant):
        buyer, _lot = buyer_with_shared_tenant
        api_client.force_authenticate(user=buyer)
        assert api_client.get(reverse("ai-forecast-yield")).status_code == status.HTTP_200_OK
        assert api_client.get(reverse("ai-forecast-price")).status_code == status.HTTP_200_OK
        assert api_client.get(reverse("ai-anomaly-list")).status_code == status.HTTP_200_OK

    def test_forecast_retrain_forbidden_for_buyer(self, api_client, buyer_with_shared_tenant):
        buyer, _lot = buyer_with_shared_tenant
        api_client.force_authenticate(user=buyer)
        r = api_client.post(reverse("ai-forecast-retrain"), {"model_type": "yield"}, format="json")
        assert r.status_code == status.HTTP_403_FORBIDDEN

    def test_monitoring_summary_ok_auditor_metrics_forbidden(
        self, api_client, buyer_with_shared_tenant
    ):
        buyer, _lot = buyer_with_shared_tenant
        api_client.force_authenticate(user=buyer)
        assert api_client.get(reverse("monitoring-summary-lite")).status_code == status.HTTP_200_OK
        assert api_client.get(reverse("monitoring-metrics")).status_code == status.HTTP_403_FORBIDDEN

    def test_privacy_export_ok(self, api_client, buyer_with_shared_tenant):
        buyer, _lot = buyer_with_shared_tenant
        api_client.force_authenticate(user=buyer)
        r = api_client.get(reverse("privacy-export-me"))
        assert r.status_code == status.HTTP_200_OK

    def test_lot_list_sees_tenant_lot(self, api_client, buyer_with_shared_tenant):
        buyer, lot = buyer_with_shared_tenant
        api_client.force_authenticate(user=buyer)
        r = api_client.get(reverse("lot-list"))
        assert r.status_code == status.HTTP_200_OK
        ids = {str(x["id"]) for x in r.data["results"]}
        assert str(lot.id) in ids

    def test_trace_events_list_ok(self, api_client, buyer_with_shared_tenant):
        buyer, lot = buyer_with_shared_tenant
        api_client.force_authenticate(user=buyer)
        r = api_client.get(reverse("trace-event-list"))
        assert r.status_code == status.HTTP_200_OK

    def test_buyer_can_post_grading_sale_event_types_only(
        self, api_client, buyer_with_shared_tenant
    ):
        buyer, lot = buyer_with_shared_tenant
        api_client.force_authenticate(user=buyer)
        bad = api_client.post(
            reverse("trace-event-list"),
            {
                "lot": str(lot.id),
                "event_type": TraceEventType.PLANTING,
                "timestamp": timezone.now().isoformat(),
                "location": "X",
            },
            format="json",
        )
        assert bad.status_code == status.HTTP_400_BAD_REQUEST
        good = api_client.post(
            reverse("trace-event-list"),
            {
                "lot": str(lot.id),
                "event_type": TraceEventType.GRADING,
                "timestamp": timezone.now().isoformat(),
                "location": "Shed",
            },
            format="json",
        )
        assert good.status_code == status.HTTP_201_CREATED
