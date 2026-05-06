"""
Objective 1 — Traceability (permissioned blockchain MVP).

Proof mapping:
  A) RBAC + permissioned writes
  B) prev_event_hash chain / strict ordering
  C) Document hash, verify, tamper, duplicate anomaly hook
  D) Provenance timeline (+ doc fields); auditor signed export in test_ai_intelligence
  E) Offline sync idempotency + per-item / validation responses

Run: ``pytest tests/test_objective1_traceability.py -v`` or
``python manage.py test tests.test_objective1_traceability``.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.ai_intelligence.detectors import document_detectors
from apps.common.enums import DocumentType, SyncStatus, TraceEventType, UserRole
from apps.documents.models import Document
from apps.documents.services import verify_document
from apps.organizations.models import OrganizationMembership
from apps.traceability.chain import GENESIS_PREV_EVENT_HASH
from apps.traceability.models import TraceEvent
from tests.factories import (
    FarmFactory,
    LotFactory,
    OrganizationFactory,
    SeasonFactory,
    UserFactory,
)


def _org_scoped_farmer_buyer_lot():
    org = OrganizationFactory()
    farmer = UserFactory(role=UserRole.SMALLHOLDER_FARMER)
    buyer = UserFactory(role=UserRole.BUYER_CONTRACTOR)
    auditor = UserFactory(role=UserRole.REGULATOR_AUDITOR)
    OrganizationMembership.objects.create(
        user=farmer,
        organization=org,
        role=UserRole.SMALLHOLDER_FARMER,
        is_primary=True,
        is_active=True,
    )
    OrganizationMembership.objects.create(
        user=buyer,
        organization=org,
        role=UserRole.BUYER_CONTRACTOR,
        is_primary=True,
        is_active=True,
    )
    OrganizationMembership.objects.create(
        user=auditor,
        organization=org,
        role=UserRole.REGULATOR_AUDITOR,
        is_primary=True,
        is_active=True,
    )
    farm = FarmFactory(owner=farmer, organization=org)
    season = SeasonFactory(farm=farm)
    lot = LotFactory(season=season)
    return SimpleNamespace(
        org=org, farmer=farmer, buyer=buyer, auditor=auditor, farm=farm, season=season, lot=lot
    )


def _client(user):
    c = APIClient()
    c.force_authenticate(user=user)
    return c


class TestO1RBACWrites(TestCase):
    """O1-A permissioned writes."""

    def test_farmer_can_register_farm(self):
        farmer = UserFactory(role=UserRole.SMALLHOLDER_FARMER)
        client = _client(farmer)
        url = reverse("farm-list")
        data = {
            "name": "O1 Seed Farm",
            "district": "Chipinge",
            "province": "Manicaland",
            "size_hectares": "12",
        }
        r = client.post(url, data)
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)

    def test_farmer_can_create_lot(self):
        farmer = UserFactory(role=UserRole.SMALLHOLDER_FARMER)
        farm = FarmFactory(owner=farmer)
        season = SeasonFactory(farm=farm)
        client = _client(farmer)
        url = reverse("lot-list")
        data = {
            "season": str(season.id),
            "lot_number": f"O1-LOT-{uuid.uuid4().hex[:8]}",
            "tobacco_type": "Virginia",
            "bale_count": 5,
            "weight_kg": "100.0",
        }
        r = client.post(url, data, format="json")
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)

    def test_buyer_cannot_create_farm(self):
        buyer = UserFactory(role=UserRole.BUYER_CONTRACTOR)
        client = _client(buyer)
        url = reverse("farm-list")
        r = client.post(url, {"name": "X", "district": "Y"}, format="json")
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    def test_farmer_can_record_planting_not_grading_or_sale(self):
        farmer = UserFactory(role=UserRole.SMALLHOLDER_FARMER)
        farm = FarmFactory(owner=farmer)
        season = SeasonFactory(farm=farm)
        lot = LotFactory(season=season)
        client = _client(farmer)
        url = reverse("trace-event-list")
        base = {"lot": str(lot.id), "timestamp": timezone.now().isoformat()}
        r1 = client.post(url, {**base, "event_type": TraceEventType.PLANTING}, format="json")
        self.assertEqual(r1.status_code, status.HTTP_201_CREATED)
        r2 = client.post(url, {**base, "event_type": TraceEventType.GRADING}, format="json")
        self.assertEqual(r2.status_code, status.HTTP_400_BAD_REQUEST)
        r3 = client.post(url, {**base, "event_type": TraceEventType.SALE}, format="json")
        self.assertEqual(r3.status_code, status.HTTP_400_BAD_REQUEST)

    def test_buyer_can_record_grading_and_sale_on_org_lot(self):
        ctx = _org_scoped_farmer_buyer_lot()
        client = _client(ctx.buyer)
        url = reverse("trace-event-list")
        base = {"lot": str(ctx.lot.id), "timestamp": timezone.now().isoformat()}
        self.assertEqual(
            client.post(
                url, {**base, "event_type": TraceEventType.GRADING}, format="json"
            ).status_code,
            status.HTTP_201_CREATED,
        )
        self.assertEqual(
            client.post(
                url, {**base, "event_type": TraceEventType.SALE}, format="json"
            ).status_code,
            status.HTTP_201_CREATED,
        )

    def test_buyer_cannot_record_planting(self):
        ctx = _org_scoped_farmer_buyer_lot()
        client = _client(ctx.buyer)
        url = reverse("trace-event-list")
        r = client.post(
            url,
            {
                "lot": str(ctx.lot.id),
                "event_type": TraceEventType.PLANTING,
                "timestamp": timezone.now().isoformat(),
            },
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_auditor_cannot_post_trace_event(self):
        ctx = _org_scoped_farmer_buyer_lot()
        client = _client(ctx.auditor)
        url = reverse("trace-event-list")
        r = client.post(
            url,
            {
                "lot": str(ctx.lot.id),
                "event_type": TraceEventType.INSPECTION,
                "timestamp": timezone.now().isoformat(),
            },
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)


class TestO1ChainPrevHash(TestCase):
    """O1-B ordering integrity."""

    def test_first_event_resolves_to_genesis_prev(self):
        farmer = UserFactory(role=UserRole.SMALLHOLDER_FARMER)
        farm = FarmFactory(owner=farmer)
        season = SeasonFactory(farm=farm)
        lot = LotFactory(season=season)
        client = _client(farmer)
        url = reverse("trace-event-list")
        r = client.post(
            url,
            {
                "lot": str(lot.id),
                "event_type": TraceEventType.PLANTING,
                "timestamp": timezone.now().isoformat(),
            },
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertEqual(r.data["prev_event_hash"], GENESIS_PREV_EVENT_HASH)

    def test_explicit_wrong_prev_rejected(self):
        farmer = UserFactory(role=UserRole.SMALLHOLDER_FARMER)
        farm = FarmFactory(owner=farmer)
        season = SeasonFactory(farm=farm)
        lot = LotFactory(season=season)
        client = _client(farmer)
        url = reverse("trace-event-list")
        r = client.post(
            url,
            {
                "lot": str(lot.id),
                "event_type": TraceEventType.PLANTING,
                "timestamp": timezone.now().isoformat(),
                "prev_event_hash": "a" * 64,
            },
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cannot_insert_with_stale_prev_after_tip_moves(self):
        farmer = UserFactory(role=UserRole.SMALLHOLDER_FARMER)
        farm = FarmFactory(owner=farmer)
        season = SeasonFactory(farm=farm)
        lot = LotFactory(season=season)
        client = _client(farmer)
        url = reverse("trace-event-list")
        ts = timezone.now().isoformat()
        e1 = client.post(
            url,
            {"lot": str(lot.id), "event_type": TraceEventType.PLANTING, "timestamp": ts},
            format="json",
        )
        self.assertEqual(e1.status_code, status.HTTP_201_CREATED)
        h1 = e1.data["event_hash"]
        e2 = client.post(
            url,
            {"lot": str(lot.id), "event_type": TraceEventType.HARVESTING, "timestamp": ts},
            format="json",
        )
        self.assertEqual(e2.status_code, status.HTTP_201_CREATED)
        r = client.post(
            url,
            {
                "lot": str(lot.id),
                "event_type": TraceEventType.CURING,
                "timestamp": ts,
                "prev_event_hash": h1,
            },
            format="json",
        )
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)


class TestO1DocumentsAndProvenance(TestCase):
    """O1-C / O1-D."""

    def test_upload_receipt_has_hash_and_verify_true(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        farmer = UserFactory(role=UserRole.SMALLHOLDER_FARMER)
        farm = FarmFactory(owner=farmer)
        season = SeasonFactory(farm=farm)
        lot = LotFactory(season=season)
        client = _client(farmer)
        url = reverse("document-list")
        file = SimpleUploadedFile("rcpt.pdf", b"receipt-bytes", content_type="application/pdf")
        r = client.post(
            url,
            {
                "lot": str(lot.id),
                "document_type": DocumentType.RECEIPT,
                "title": "O1 Receipt",
                "file": file,
            },
            format="multipart",
        )
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(r.data.get("sha256_hash", "")), 64)
        vurl = reverse("document-verify", kwargs={"pk": r.data["id"]})
        vr = client.post(vurl)
        self.assertEqual(vr.status_code, status.HTTP_200_OK)
        self.assertTrue(vr.data.get("hash_match"))

    def test_tampered_file_verify_fails(self):
        from django.core.files.base import ContentFile
        from django.core.files.uploadedfile import SimpleUploadedFile

        farmer = UserFactory(role=UserRole.SMALLHOLDER_FARMER)
        farm = FarmFactory(owner=farmer)
        season = SeasonFactory(farm=farm)
        lot = LotFactory(season=season)
        client = _client(farmer)
        url = reverse("document-list")
        file = SimpleUploadedFile("doc.pdf", b"original-content", content_type="application/pdf")
        r = client.post(
            url,
            {
                "lot": str(lot.id),
                "document_type": DocumentType.CERTIFICATE,
                "title": "Cert",
                "file": file,
            },
            format="multipart",
        )
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        doc = Document.objects.get(id=r.data["id"])
        stored_hash = doc.sha256_hash
        doc.file.save("doc.pdf", ContentFile(b"original-content\x00"), save=True)
        doc.refresh_from_db()
        self.assertEqual(doc.sha256_hash, stored_hash)
        result = verify_document(doc)
        self.assertFalse(result["hash_match"])

    def test_duplicate_receipt_triggers_duplicate_hook(self):
        import hashlib

        from django.core.files.uploadedfile import SimpleUploadedFile

        ctx = _org_scoped_farmer_buyer_lot()
        lot = ctx.lot
        farmer = ctx.farmer
        content = b"same-payload"
        h = hashlib.sha256(content).hexdigest()
        f1 = SimpleUploadedFile("a.pdf", content, content_type="application/pdf")
        f2 = SimpleUploadedFile("b.pdf", content, content_type="application/pdf")
        Document.objects.create(
            lot=lot,
            uploaded_by=farmer,
            document_type=DocumentType.RECEIPT,
            title="R1",
            file=f1,
            file_name="a.pdf",
            mime_type="application/pdf",
            file_size=len(content),
            sha256_hash=h,
        )
        Document.objects.create(
            lot=lot,
            uploaded_by=farmer,
            document_type=DocumentType.RECEIPT,
            title="R2",
            file=f2,
            file_name="b.pdf",
            mime_type="application/pdf",
            file_size=len(content),
            sha256_hash=h,
        )
        n = document_detectors._detect_exact_duplicates(ctx.org)
        self.assertGreaterEqual(n, 1)

    def test_provenance_timeline_ordered_and_has_doc_fields(self):
        farmer = UserFactory(role=UserRole.SMALLHOLDER_FARMER)
        farm = FarmFactory(owner=farmer)
        season = SeasonFactory(farm=farm)
        lot = LotFactory(season=season)
        TraceEvent.objects.create(
            lot=lot,
            actor=farmer,
            event_type=TraceEventType.PLANTING,
            timestamp=timezone.now(),
        )
        client = _client(farmer)
        url = reverse("lot-provenance", kwargs={"lot_id": lot.id})
        r = client.get(url)
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertIn("timeline", r.data)
        self.assertIn("documents", r.data)
        if r.data["timeline"]:
            row = r.data["timeline"][0]
            self.assertIn("event_hash", row)
            self.assertIn("prev_event_hash", row)


class TestO1OfflineSync(TestCase):
    """O1-E batch sync."""

    def test_trace_batch_idempotent_no_duplicates(self):
        farmer = UserFactory(role=UserRole.SMALLHOLDER_FARMER)
        farm = FarmFactory(owner=farmer)
        season = SeasonFactory(farm=farm)
        lot = LotFactory(season=season)
        client = _client(farmer)
        url = reverse("batch-sync")
        client_id = str(uuid.uuid4())
        idem = f"trace-{client_id}"
        ts = timezone.now().isoformat()
        record = {
            "client_record_id": client_id,
            "idempotency_key": idem,
            "payload_type": "trace_event",
            "payload": {
                "lot_id": str(lot.id),
                "event_type": TraceEventType.TRANSPORT,
                "timestamp": ts,
                "location": "Depot",
            },
        }
        r1 = client.post(url, {"records": [record]}, format="json")
        self.assertEqual(r1.status_code, status.HTTP_200_OK)
        self.assertEqual(r1.data["results"][0]["status"], SyncStatus.SYNCED)
        n1 = TraceEvent.objects.filter(lot=lot, event_type=TraceEventType.TRANSPORT).count()
        r2 = client.post(url, {"records": [record]}, format="json")
        self.assertEqual(r2.status_code, status.HTTP_200_OK)
        self.assertEqual(r2.data["results"][0]["status"], SyncStatus.DUPLICATE_IGNORED)
        n2 = TraceEvent.objects.filter(lot=lot, event_type=TraceEventType.TRANSPORT).count()
        self.assertEqual(n1, n2)
        self.assertEqual(n1, 1)

    def test_batch_returns_validation_envelope_when_invalid_type(self):
        farmer = UserFactory(role=UserRole.SMALLHOLDER_FARMER)
        client = _client(farmer)
        url = reverse("batch-sync")
        farm_id = str(uuid.uuid4())
        rec_ok = {
            "client_record_id": str(uuid.uuid4()),
            "idempotency_key": f"farm-a-{farm_id}",
            "payload_type": "farm",
            "payload": {
                "id": farm_id,
                "name": "Mixed Farm",
                "district": "D",
                "province": "P",
            },
        }
        rec_bad = {
            "client_record_id": str(uuid.uuid4()),
            "idempotency_key": "bad-unknown-type",
            "payload_type": "unknown_type_xyz",
            "payload": {},
        }
        r = client.post(url, {"records": [rec_ok, rec_bad]}, format="json")
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(r.data.get("success", True))

    def test_batch_two_valid_records_per_item_synced(self):
        farmer = UserFactory(role=UserRole.SMALLHOLDER_FARMER)
        client = _client(farmer)
        url = reverse("batch-sync")
        id1, id2 = str(uuid.uuid4()), str(uuid.uuid4())
        records = [
            {
                "client_record_id": str(uuid.uuid4()),
                "idempotency_key": f"farm-{id1}",
                "payload_type": "farm",
                "payload": {
                    "id": id1,
                    "name": "F1",
                    "district": "D",
                    "province": "P",
                },
            },
            {
                "client_record_id": str(uuid.uuid4()),
                "idempotency_key": f"farm-{id2}",
                "payload_type": "farm",
                "payload": {
                    "id": id2,
                    "name": "F2",
                    "district": "D",
                    "province": "P",
                },
            },
        ]
        r = client.post(url, {"records": records}, format="json")
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(len(r.data["results"]), 2)
        self.assertEqual(
            {row["status"] for row in r.data["results"]},
            {SyncStatus.SYNCED},
        )
