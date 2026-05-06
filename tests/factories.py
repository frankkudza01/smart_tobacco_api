import factory
from datetime import date, timedelta
from decimal import Decimal
from django.utils import timezone

from apps.accounts.models import User, FarmerProfile, BuyerProfile
from apps.common.enums import (
    LotStatus, SaleType, SeasonStatus, SettlementStatus,
    TraceEventType, UserRole,
)
from apps.farms.models import Farm
from apps.lots.models import Lot
from apps.organizations.models import Organization, OrganizationMembership
from apps.seasons.models import FarmSeasonAssociation, Season
from apps.sales.models import Sale
from apps.settlements.models import Settlement
from apps.traceability.models import TraceEvent


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User

    email = factory.Sequence(lambda n: f"user{n}@test.com")
    first_name = factory.Faker("first_name")
    last_name = factory.Faker("last_name")
    role = UserRole.SMALLHOLDER_FARMER
    is_active = True

    @factory.post_generation
    def password(self, create, extracted, **kwargs):
        self.set_password(extracted or "testpass123")
        if create:
            self.save()


class FarmerFactory(UserFactory):
    role = UserRole.SMALLHOLDER_FARMER

    @factory.post_generation
    def profile(self, create, extracted, **kwargs):
        if create:
            FarmerProfile.objects.create(
                user=self,
                national_id=factory.Faker("ssn").generate(),
                district="Mvurwi",
            )


class BuyerFactory(UserFactory):
    role = UserRole.BUYER_CONTRACTOR

    @factory.post_generation
    def profile(self, create, extracted, **kwargs):
        if create:
            BuyerProfile.objects.create(
                user=self,
                company_name="Test Buyer Co",
            )

    @factory.post_generation
    def link_organization(self, create, extracted, **kwargs):
        """Attach a tenant org so buyer-scoped APIs (preferences, AI, monitoring) work."""
        if not create:
            return
        if extracted is False:
            return
        org = extracted if isinstance(extracted, Organization) else OrganizationFactory()
        OrganizationMembership.objects.get_or_create(
            user=self,
            organization=org,
            defaults={
                "role": UserRole.BUYER_CONTRACTOR,
                "is_primary": True,
                "is_active": True,
            },
        )


class AdminFactory(UserFactory):
    role = UserRole.SYSTEM_ADMIN
    is_staff = True


class AuditorFactory(UserFactory):
    role = UserRole.REGULATOR_AUDITOR


class OrganizationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Organization

    name = factory.Sequence(lambda n: f"Org {n}")
    org_type = "cooperative"


class FarmFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Farm

    owner = factory.SubFactory(FarmerFactory)
    name = factory.Sequence(lambda n: f"Farm {n}")
    district = "Mvurwi"
    province = "Mashonaland Central"
    size_hectares = Decimal("10.0")


class SeasonFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Season

    crop_year = factory.Sequence(lambda n: 2000 + n)
    status = SeasonStatus.ACTIVE
    planting_date = factory.LazyFunction(lambda: date.today() - timedelta(days=120))

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        farm = kwargs.pop("farm", None)
        season = super()._create(model_class, *args, **kwargs)
        if farm is not None:
            FarmSeasonAssociation.objects.get_or_create(farm=farm, season=season)
        return season


class LotFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Lot

    farm = factory.SubFactory(FarmFactory)
    season = factory.SubFactory(SeasonFactory)
    created_by = factory.LazyAttribute(lambda o: o.farm.owner)

    @factory.post_generation
    def link_farm_season(self, create, extracted, **kwargs):
        if create:
            FarmSeasonAssociation.objects.get_or_create(farm=self.farm, season=self.season)
    lot_number = factory.Sequence(lambda n: f"LOT-TEST-{n:04d}")
    weight_kg = Decimal("500.0")
    bale_count = 10
    tobacco_type = "Virginia Flue-Cured"
    status = LotStatus.REGISTERED


class TraceEventFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = TraceEvent

    lot = factory.SubFactory(LotFactory)
    actor = factory.LazyAttribute(lambda o: o.lot.farm.owner)
    event_type = TraceEventType.PLANTING
    timestamp = factory.LazyFunction(timezone.now)
    location = "Test Field"


class SaleFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Sale

    lot = factory.SubFactory(LotFactory)
    buyer = factory.SubFactory(BuyerFactory)
    sale_type = SaleType.AUCTION
    price_per_kg = Decimal("4.00")
    total_weight_kg = Decimal("500.0")
    total_amount = Decimal("2000.0")
    sale_date = factory.LazyFunction(timezone.now)


class SettlementFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Settlement

    sale = factory.SubFactory(SaleFactory)
    farmer = factory.LazyAttribute(lambda o: o.sale.lot.farm.owner)
    created_by = factory.LazyAttribute(lambda o: o.sale.buyer)
    amount_due = Decimal("2000.0")
    amount_paid = Decimal("0")
    status = SettlementStatus.PENDING
