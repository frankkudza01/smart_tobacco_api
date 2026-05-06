"""
End-to-end scenario test:
1. Farmer registers farm and season
2. Farmer records planting event
3. Farmer uploads receipt
4. Buyer records grading and sale
5. Settlement is created
6. Farmer views settlement
7. Dispute is raised
8. Auditor queries provenance
9. Document verification succeeds
"""
import uuid

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.accounts.services import register_user
from apps.common.enums import (
    DisputeStatus, DocumentType, LotStatus, SaleType,
    SeasonStatus, SettlementStatus, TraceEventType, UserRole,
)


@pytest.mark.django_db
class TestEndToEndScenario:
    def test_full_tobacco_lifecycle(self):
        # --- Setup users ---
        farmer = register_user(
            email="e2e_farmer@test.com", password="pass12345",
            first_name="E2E", last_name="Farmer",
            role=UserRole.SMALLHOLDER_FARMER,
            profile_data={"national_id": "99-000001-X-00"},
        )
        buyer = register_user(
            email="e2e_buyer@test.com", password="pass12345",
            first_name="E2E", last_name="Buyer",
            role=UserRole.BUYER_CONTRACTOR,
            profile_data={"company_name": "E2E Buyers Ltd"},
        )
        auditor = register_user(
            email="e2e_auditor@test.com", password="pass12345",
            first_name="E2E", last_name="Auditor",
            role=UserRole.REGULATOR_AUDITOR,
            profile_data={"department": "QA"},
        )

        farmer_client = APIClient()
        farmer_client.force_authenticate(user=farmer)
        buyer_client = APIClient()
        buyer_client.force_authenticate(user=buyer)
        auditor_client = APIClient()
        auditor_client.force_authenticate(user=auditor)

        # 1. Farmer creates farm
        resp = farmer_client.post(reverse("farm-list"), {
            "name": "E2E Farm",
            "district": "Mvurwi",
            "province": "Mashonaland Central",
            "size_hectares": "10.0",
        })
        assert resp.status_code == status.HTTP_201_CREATED
        farm_id = resp.data["id"]

        # 1b. Farmer creates season
        resp = farmer_client.post(reverse("season-list"), {
            "farm": farm_id,
            "crop_year": 2025,
            "status": SeasonStatus.ACTIVE,
            "planting_date": "2024-09-15",
        })
        assert resp.status_code == status.HTTP_201_CREATED
        season_id = resp.data["id"]

        # 1c. Farmer creates lot
        resp = farmer_client.post(reverse("lot-list"), {
            "season": season_id,
            "lot_number": f"LOT-E2E-{uuid.uuid4().hex[:6]}",
            "weight_kg": "500.00",
            "bale_count": 10,
            "tobacco_type": "Virginia",
        })
        assert resp.status_code == status.HTTP_201_CREATED
        lot_id = resp.data["id"]

        # 2. Farmer records planting event
        resp = farmer_client.post(reverse("trace-event-list"), {
            "lot": lot_id,
            "event_type": TraceEventType.PLANTING,
            "timestamp": timezone.now().isoformat(),
            "location": "Field A",
            "payload": {"seed_variety": "KRK26"},
        }, format="json")
        assert resp.status_code == status.HTTP_201_CREATED
        assert resp.data["event_hash"] != ""

        # 3. Farmer uploads receipt
        file = SimpleUploadedFile("receipt.pdf", b"receipt content", content_type="application/pdf")
        resp = farmer_client.post(reverse("document-list"), {
            "lot": lot_id,
            "document_type": DocumentType.RECEIPT,
            "title": "Seed Receipt",
            "file": file,
        }, format="multipart")
        assert resp.status_code == status.HTTP_201_CREATED
        doc_id = resp.data["id"]
        assert resp.data["sha256_hash"] != ""

        # 5. Buyer records grading
        resp = buyer_client.post(reverse("grading-list"), {
            "lot": lot_id,
            "grade": "C1L",
            "weight_kg": "500.00",
            "moisture_percent": "12.5",
            "quality_score": 85,
            "graded_at": timezone.now().isoformat(),
        })
        assert resp.status_code == status.HTTP_201_CREATED

        # 5b. Buyer records sale
        resp = buyer_client.post(reverse("sale-list"), {
            "lot": lot_id,
            "sale_type": SaleType.AUCTION,
            "price_per_kg": "4.50",
            "total_weight_kg": "500.00",
            "total_amount": "2250.00",
            "sale_date": timezone.now().isoformat(),
        })
        assert resp.status_code == status.HTTP_201_CREATED
        sale_id = resp.data["id"]

        # 6. Buyer creates settlement
        resp = buyer_client.post(reverse("settlement-list"), {
            "sale": sale_id,
            "farmer": str(farmer.id),
            "amount_due": "2250.00",
            "amount_paid": "2250.00",
            "currency": "USD",
            "status": SettlementStatus.PAID,
            "payment_reference": "PAY-E2E-001",
            "payment_method": "bank_transfer",
            "payment_date": timezone.now().isoformat(),
        })
        assert resp.status_code == status.HTTP_201_CREATED

        # 7. Farmer views settlements
        resp = farmer_client.get(reverse("settlement-list"))
        assert resp.status_code == status.HTTP_200_OK
        assert len(resp.data["results"]) == 1
        assert resp.data["results"][0]["status"] == SettlementStatus.PAID

        # 8. Farmer raises dispute
        resp = farmer_client.post(reverse("dispute-list"), {
            "lot": lot_id,
            "sale": sale_id,
            "title": "Grade dispute",
            "description": "I believe grade should be higher.",
        })
        assert resp.status_code == status.HTTP_201_CREATED
        dispute_id = resp.data["id"]

        # 9. Auditor queries provenance
        resp = auditor_client.get(reverse("lot-provenance", kwargs={"lot_id": lot_id}))
        assert resp.status_code == status.HTTP_200_OK
        assert len(resp.data["timeline"]) >= 1
        assert len(resp.data["documents"]) >= 1
        assert len(resp.data["grades"]) >= 1
        assert len(resp.data["sales"]) >= 1

        # 10. Document verification
        resp = auditor_client.post(reverse("document-verify", kwargs={"pk": doc_id}))
        assert resp.status_code == status.HTTP_200_OK
        assert "hash_match" in resp.data
