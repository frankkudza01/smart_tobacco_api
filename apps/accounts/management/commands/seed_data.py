"""
Management command to seed the database with realistic test data.
Usage: python manage.py seed_data
"""
from datetime import date, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.accounts.models import AdminProfile, AuditorProfile, BuyerProfile, FarmerProfile
from apps.accounts.seed_constants import SEED_ORGANIZATION_REGISTRATION_NUMBERS, SEED_PHONE_NUMBERS
from apps.accounts.services import register_user
from apps.common.enums import (
    DisputeStatus, DocumentType, LotStatus, NotificationType,
    SaleType, SeasonStatus, SettlementStatus, TraceEventType, UserRole,
)
from apps.disputes.models import Dispute
from apps.farms.models import Farm
from apps.grading.models import GradeRecord
from apps.lots.models import Lot
from apps.notifications.services import create_notification
from apps.organizations.models import BuyerLotAssignment, Organization, OrganizationMembership
from apps.sales.models import Sale
from apps.seasons.models import Season
from apps.settlements.models import Settlement
from apps.traceability.services import create_trace_event


class Command(BaseCommand):
    help = "Seed database with realistic test data for all stakeholder roles"

    def handle(self, *args, **options):
        self.stdout.write("Seeding data...")

        # Organizations
        org_timb = Organization.objects.create(
            name="Tobacco Industry and Marketing Board (TIMB)",
            org_type="regulator",
            registration_number=SEED_ORGANIZATION_REGISTRATION_NUMBERS[0],
        )
        org_mashonaland = Organization.objects.create(
            name="Mashonaland Tobacco Co-operative",
            org_type="cooperative",
            registration_number=SEED_ORGANIZATION_REGISTRATION_NUMBERS[1],
        )
        org_buyer = Organization.objects.create(
            name="Zimbabwe Leaf Tobacco",
            org_type="buyer",
            registration_number=SEED_ORGANIZATION_REGISTRATION_NUMBERS[2],
        )

        # Users
        farmer1 = register_user(
            email="tafadzwa@example.com",
            password="farmer12345",
            first_name="Tafadzwa",
            last_name="Moyo",
            role=UserRole.SMALLHOLDER_FARMER,
            phone_number=SEED_PHONE_NUMBERS[0],
            profile_data={
                "national_id": "63-123456-A-78",
                "district": "Mvurwi",
                "ward": "Ward 5",
                "village": "Chikwaka",
                "bank_name": "CBZ Bank",
                "bank_account_number": "1234567890",
                "mobile_money_number": SEED_PHONE_NUMBERS[0],
                "years_of_experience": 8,
            },
        )

        farmer2 = register_user(
            email="chipo@example.com",
            password="farmer12345",
            first_name="Chipo",
            last_name="Ndlovu",
            role=UserRole.SMALLHOLDER_FARMER,
            phone_number=SEED_PHONE_NUMBERS[1],
            profile_data={
                "national_id": "63-234567-B-89",
                "district": "Karoi",
                "ward": "Ward 3",
                "village": "Mushumbi",
                "years_of_experience": 5,
            },
        )

        buyer1 = register_user(
            email="james@zlt.co.zw",
            password="buyer12345",
            first_name="James",
            last_name="Makoni",
            role=UserRole.BUYER_CONTRACTOR,
            phone_number=SEED_PHONE_NUMBERS[2],
            profile_data={
                "company_name": "Zimbabwe Leaf Tobacco",
                "license_number": "BL-2024-0042",
                "buyer_type": "merchant",
            },
            skip_buyer_organization=True,
        )

        auditor1 = register_user(
            email="grace@timb.gov.zw",
            password="auditor12345",
            first_name="Grace",
            last_name="Chirwa",
            role=UserRole.REGULATOR_AUDITOR,
            phone_number=SEED_PHONE_NUMBERS[3],
            profile_data={
                "department": "Quality & Compliance",
                "badge_number": "TIMB-AUD-042",
                "jurisdiction": "Mashonaland Central",
            },
        )

        admin1 = register_user(
            email="admin@tobacco.zw",
            password="admin12345",
            first_name="System",
            last_name="Administrator",
            role=UserRole.SYSTEM_ADMIN,
            profile_data={"department": "IT"},
        )
        admin1.is_staff = True
        admin1.is_superuser = True
        admin1.save()

        # Memberships
        OrganizationMembership.objects.create(user=farmer1, organization=org_mashonaland, role=UserRole.SMALLHOLDER_FARMER, is_primary=True)
        OrganizationMembership.objects.create(user=farmer2, organization=org_mashonaland, role=UserRole.SMALLHOLDER_FARMER, is_primary=True)
        # Buyer + auditor + admin share the cooperative tenant for end-to-end RBAC demos (TIMB kept as secondary org).
        OrganizationMembership.objects.create(user=buyer1, organization=org_mashonaland, role=UserRole.BUYER_CONTRACTOR, is_primary=True)
        OrganizationMembership.objects.create(user=buyer1, organization=org_buyer, role=UserRole.BUYER_CONTRACTOR, is_primary=False)
        OrganizationMembership.objects.create(user=auditor1, organization=org_mashonaland, role=UserRole.REGULATOR_AUDITOR, is_primary=True)
        OrganizationMembership.objects.create(user=auditor1, organization=org_timb, role=UserRole.REGULATOR_AUDITOR, is_primary=False)
        OrganizationMembership.objects.create(user=admin1, organization=org_mashonaland, role=UserRole.SYSTEM_ADMIN, is_primary=True)

        # Farms
        farm1 = Farm.objects.create(
            owner=farmer1,
            organization=org_mashonaland,
            name="Moyo Tobacco Farm",
            location_description="Plot 42, Mvurwi Farming Area",
            latitude=Decimal("-17.0344"),
            longitude=Decimal("30.5217"),
            size_hectares=Decimal("12.5"),
            district="Mvurwi",
            province="Mashonaland Central",
        )

        farm2 = Farm.objects.create(
            owner=farmer2,
            organization=org_mashonaland,
            name="Ndlovu Family Farm",
            location_description="Karoi Communal Lands",
            latitude=Decimal("-16.8100"),
            longitude=Decimal("29.6920"),
            size_hectares=Decimal("8.0"),
            district="Karoi",
            province="Mashonaland West",
        )

        # Seasons
        season1 = Season.objects.create(
            farm=farm1,
            crop_year=2025,
            name="2025 Main Season",
            status=SeasonStatus.ACTIVE,
            planting_date=date(2024, 9, 15),
            expected_harvest_date=date(2025, 3, 1),
            expected_yield_kg=Decimal("2500"),
        )

        season2 = Season.objects.create(
            farm=farm2,
            crop_year=2025,
            name="2025 Season",
            status=SeasonStatus.ACTIVE,
            planting_date=date(2024, 10, 1),
            expected_harvest_date=date(2025, 3, 15),
            expected_yield_kg=Decimal("1800"),
        )

        # Lots
        lot1 = Lot.objects.create(
            season=season1,
            created_by=farmer1,
            lot_number="LOT-MVR-2025-001",
            description="Virginia flue-cured, barn A",
            weight_kg=Decimal("500"),
            bale_count=10,
            tobacco_type="Virginia Flue-Cured",
            status=LotStatus.SOLD,
        )

        lot2 = Lot.objects.create(
            season=season1,
            created_by=farmer1,
            lot_number="LOT-MVR-2025-002",
            description="Virginia flue-cured, barn B",
            weight_kg=Decimal("350"),
            bale_count=7,
            tobacco_type="Virginia Flue-Cured",
            status=LotStatus.GRADED,
        )

        lot3 = Lot.objects.create(
            season=season2,
            created_by=farmer2,
            lot_number="LOT-KAR-2025-001",
            description="Burley air-cured",
            weight_kg=Decimal("400"),
            bale_count=8,
            tobacco_type="Burley",
            status=LotStatus.REGISTERED,
        )

        BuyerLotAssignment.objects.create(organization=org_mashonaland, buyer=buyer1, lot=lot2)

        # Trace Events
        now = timezone.now()
        create_trace_event(
            lot=lot1, actor=farmer1, event_type=TraceEventType.PLANTING,
            timestamp=now - timedelta(days=180), location="Plot 42 Field A",
            payload={"seed_variety": "KRK26", "area_ha": 3.0},
        )
        create_trace_event(
            lot=lot1, actor=farmer1, event_type=TraceEventType.HARVESTING,
            timestamp=now - timedelta(days=60), location="Plot 42 Field A",
            payload={"green_weight_kg": 800},
        )
        create_trace_event(
            lot=lot1, actor=farmer1, event_type=TraceEventType.CURING,
            timestamp=now - timedelta(days=45), location="Barn A",
            payload={"method": "flue_cured", "duration_days": 7},
        )
        create_trace_event(
            lot=lot1, actor=buyer1, event_type=TraceEventType.GRADING,
            timestamp=now - timedelta(days=20),
            location="Mvurwi Auction Floor",
        )
        create_trace_event(
            lot=lot1, actor=buyer1, event_type=TraceEventType.SALE,
            timestamp=now - timedelta(days=15),
            location="Mvurwi Auction Floor",
            payload={"auction_ref": "AUC-MVR-2025-0042"},
        )

        # Grading
        GradeRecord.objects.create(
            lot=lot1, graded_by=buyer1, grade="C1L",
            weight_kg=Decimal("500"), moisture_percent=Decimal("12.5"),
            quality_score=82, graded_at=now - timedelta(days=20),
            notes="Good color, acceptable moisture",
        )

        GradeRecord.objects.create(
            lot=lot2, graded_by=buyer1, grade="C2L",
            weight_kg=Decimal("350"), moisture_percent=Decimal("13.2"),
            quality_score=74, graded_at=now - timedelta(days=5),
        )

        # Sales
        sale1 = Sale.objects.create(
            lot=lot1, buyer=buyer1, sale_type=SaleType.AUCTION,
            price_per_kg=Decimal("4.20"), total_weight_kg=Decimal("500"),
            total_amount=Decimal("2100.00"), currency="USD",
            sale_date=now - timedelta(days=15),
            auction_floor_reference="AUC-MVR-2025-0042",
        )

        # Settlements
        Settlement.objects.create(
            sale=sale1, farmer=farmer1, created_by=buyer1,
            amount_due=Decimal("2100.00"), amount_paid=Decimal("1500.00"),
            currency="USD", status=SettlementStatus.PARTIAL,
            payment_reference="PAY-2025-001",
            payment_method="bank_transfer",
            payment_date=now - timedelta(days=10),
            due_date=(now + timedelta(days=20)).date(),
        )

        # Disputes
        dispute1 = Dispute.objects.create(
            lot=lot1, sale=sale1, raised_by=farmer1,
            assigned_to=buyer1,
            title="Grading dispute on Lot MVR-2025-001",
            description="I believe the grade assigned (C1L) undervalues the quality of my tobacco. "
                        "The moisture reading was within acceptable range and color was excellent.",
            status=DisputeStatus.UNDER_REVIEW,
        )

        # Notifications
        create_notification(
            recipient=farmer1, notification_type=NotificationType.SETTLEMENT,
            title="Partial payment received",
            body="USD 1,500.00 received for Lot LOT-MVR-2025-001.",
            reference_type="settlement", reference_id=sale1.id,
        )
        create_notification(
            recipient=farmer1, notification_type=NotificationType.DISPUTE,
            title="Dispute under review",
            body="Your dispute on grading has been assigned for review.",
            reference_type="dispute", reference_id=dispute1.id,
        )
        create_notification(
            recipient=buyer1, notification_type=NotificationType.ACTION_REQUIRED,
            title="Dispute response needed",
            body="Farmer Tafadzwa Moyo has raised a grading dispute on Lot LOT-MVR-2025-001.",
            reference_type="dispute", reference_id=dispute1.id,
        )

        self.stdout.write(self.style.SUCCESS("Seed data created successfully!"))
        self.stdout.write(f"  Farmers: tafadzwa@example.com / farmer12345")
        self.stdout.write(f"           chipo@example.com / farmer12345")
        self.stdout.write(f"  Buyer:   james@zlt.co.zw / buyer12345")
        self.stdout.write(f"  Auditor: grace@timb.gov.zw / auditor12345")
        self.stdout.write(f"  Admin:   admin@tobacco.zw / admin12345")
