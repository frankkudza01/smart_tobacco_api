import pytest
from rest_framework.test import APIClient

from tests.factories import (
    AdminFactory,
    AuditorFactory,
    BuyerFactory,
    FarmerFactory,
    FarmFactory,
    LotFactory,
    OrganizationFactory,
    SeasonFactory,
)


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def farmer_user(db):
    return FarmerFactory()


@pytest.fixture
def buyer_user(db):
    return BuyerFactory()


@pytest.fixture
def admin_user(db):
    return AdminFactory()


@pytest.fixture
def auditor_user(db):
    return AuditorFactory()


@pytest.fixture
def organization(db):
    return OrganizationFactory()


@pytest.fixture
def farm(db, farmer_user):
    return FarmFactory(owner=farmer_user)


@pytest.fixture
def season(db, farm):
    return SeasonFactory(farm=farm)


@pytest.fixture
def lot(db, season):
    return LotFactory(season=season)


@pytest.fixture
def authenticated_farmer_client(api_client, farmer_user):
    api_client.force_authenticate(user=farmer_user)
    return api_client


@pytest.fixture
def authenticated_buyer_client(api_client, buyer_user):
    api_client.force_authenticate(user=buyer_user)
    return api_client


@pytest.fixture
def authenticated_admin_client(api_client, admin_user):
    api_client.force_authenticate(user=admin_user)
    return api_client


@pytest.fixture
def authenticated_auditor_client(api_client, auditor_user):
    api_client.force_authenticate(user=auditor_user)
    return api_client
