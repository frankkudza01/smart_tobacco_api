"""Cross-field and tenancy validations for sales, settlements, and trace writes."""
import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework import status

from apps.common.enums import LotStatus, SaleType, SettlementStatus, TraceEventType, UserRole
from apps.organizations.models import OrganizationMembership
from tests.factories import (
    BuyerFactory,
    FarmFactory,
    FarmerFactory,
    LotFactory,
    OrganizationFactory,
    SaleFactory,
    SeasonFactory,
)


@pytest.fixture
def buyer_lot_org(db):
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
    lot = LotFactory(season=season, farm=farm, status=LotStatus.REGISTERED, bale_count=10)
    return buyer, farmer, lot


@pytest.fixture
def buyer_owned_sale(buyer_lot_org):
    buyer, farmer, lot = buyer_lot_org
    sale = SaleFactory(lot=lot, buyer=buyer)
    return buyer, farmer, lot, sale


@pytest.mark.django_db
class TestSaleSerializerValidation:
    def test_sale_rejects_line_total_mismatch(self, api_client, buyer_lot_org):
        buyer, _farmer, lot = buyer_lot_org
        api_client.force_authenticate(user=buyer)
        resp = api_client.post(
            reverse("sale-list"),
            {
                "lot": str(lot.id),
                "sale_type": SaleType.AUCTION,
                "price_per_kg": "4.00",
                "total_weight_kg": "100.00",
                "total_amount": "999.00",
                "currency": "usd",
                "sale_date": timezone.now().isoformat(),
            },
            format="json",
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert "total_amount" in resp.data

    def test_sale_accepts_matching_line_total(self, api_client, buyer_lot_org):
        buyer, _farmer, lot = buyer_lot_org
        api_client.force_authenticate(user=buyer)
        resp = api_client.post(
            reverse("sale-list"),
            {
                "lot": str(lot.id),
                "sale_type": SaleType.AUCTION,
                "price_per_kg": "4.00",
                "total_weight_kg": "100.00",
                "total_amount": "400.00",
                "currency": "usd",
                "sale_date": timezone.now().isoformat(),
            },
            format="json",
        )
        assert resp.status_code == status.HTTP_201_CREATED


@pytest.mark.django_db
class TestSettlementSerializerValidation:
    def test_settlement_rejects_wrong_farmer(self, api_client, buyer_owned_sale):
        buyer, farmer, _lot, sale = buyer_owned_sale
        other = FarmerFactory()
        api_client.force_authenticate(user=buyer)
        resp = api_client.post(
            reverse("settlement-list"),
            {
                "sale": str(sale.id),
                "farmer": str(other.id),
                "amount_due": "100.00",
                "amount_paid": "0",
                "currency": "USD",
                "status": SettlementStatus.PENDING,
            },
            format="json",
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert "farmer" in resp.data

    def test_settlement_rejects_sale_not_owned_by_buyer(self, api_client, buyer_owned_sale):
        buyer, farmer, lot, _sale = buyer_owned_sale
        other_buyer = BuyerFactory()
        other_sale = SaleFactory(lot=lot, buyer=other_buyer)
        api_client.force_authenticate(user=buyer)
        resp = api_client.post(
            reverse("settlement-list"),
            {
                "sale": str(other_sale.id),
                "farmer": str(farmer.id),
                "amount_due": "100.00",
                "amount_paid": "0",
                "currency": "USD",
                "status": SettlementStatus.PENDING,
            },
            format="json",
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert "sale" in resp.data


@pytest.mark.django_db
class TestTraceEventLotAccess:
    def test_buyer_cannot_post_trace_to_foreign_org_lot(self, api_client, buyer_lot_org):
        buyer, _farmer, _lot = buyer_lot_org
        outsider = FarmerFactory()
        foreign_farm = FarmFactory(owner=outsider)
        foreign_season = SeasonFactory(farm=foreign_farm)
        foreign_lot = LotFactory(season=foreign_season, farm=foreign_farm)

        api_client.force_authenticate(user=buyer)
        resp = api_client.post(
            reverse("trace-event-list"),
            {
                "lot": str(foreign_lot.id),
                "event_type": TraceEventType.GRADING,
                "timestamp": timezone.now().isoformat(),
                "location": "Elsewhere",
            },
            format="json",
        )
        assert resp.status_code == status.HTTP_403_FORBIDDEN
