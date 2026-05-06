"""
Distinction extensions — RBAC, tenancy, i18n preferences, monitoring gates, dispute analytics.

Run: ``pytest tests/test_distinction_extensions.py -v``
"""
from __future__ import annotations

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.common.enums import DocumentType, UserRole
from apps.documents.models import Document
from apps.organizations.models import OrganizationMembership
from apps.worldready.models import UserPreference
from tests.factories import FarmFactory, OrganizationFactory, UserFactory


def _client(user):
    c = APIClient()
    c.force_authenticate(user=user)
    return c


def _membership(user, org, role):
    OrganizationMembership.objects.create(
        user=user,
        organization=org,
        role=role,
        is_primary=True,
        is_active=True,
    )


def test_preferences_requires_organization_membership(db):
    farmer = UserFactory(role=UserRole.SMALLHOLDER_FARMER)
    FarmFactory(owner=farmer)  # no org on farm → no tenant
    resp = _client(farmer).get(reverse("preferences-me"))
    assert resp.status_code == status.HTTP_403_FORBIDDEN


def test_preferences_patch_language_shona(db):
    org = OrganizationFactory()
    farmer = UserFactory(role=UserRole.SMALLHOLDER_FARMER)
    _membership(farmer, org, UserRole.SMALLHOLDER_FARMER)
    FarmFactory(owner=farmer, organization=org)
    c = _client(farmer)
    resp = c.patch(reverse("preferences-me"), {"preferred_language": "sn"}, format="json")
    assert resp.status_code == status.HTTP_200_OK
    assert resp.data["preferred_language"] == "sn"
    pref = UserPreference.objects.get(user=farmer, organization=org)
    assert pref.preferred_language == "sn"


def test_i18n_strings_returns_keys(db):
    org = OrganizationFactory()
    farmer = UserFactory(role=UserRole.SMALLHOLDER_FARMER)
    _membership(farmer, org, UserRole.SMALLHOLDER_FARMER)
    FarmFactory(owner=farmer, organization=org)
    resp = _client(farmer).get(reverse("i18n-strings"), {"lang": "sn"})
    assert resp.status_code == status.HTTP_200_OK
    assert resp.data["lang"] == "sn"
    assert isinstance(resp.data.get("strings"), dict)
    assert len(resp.data["strings"]) > 0


def test_monitoring_metrics_forbidden_for_farmer(db):
    org = OrganizationFactory()
    farmer = UserFactory(role=UserRole.SMALLHOLDER_FARMER)
    _membership(farmer, org, UserRole.SMALLHOLDER_FARMER)
    FarmFactory(owner=farmer, organization=org)
    resp = _client(farmer).get(reverse("monitoring-metrics"))
    assert resp.status_code == status.HTTP_403_FORBIDDEN


def test_monitoring_metrics_ok_for_auditor(db):
    org = OrganizationFactory()
    auditor = UserFactory(role=UserRole.REGULATOR_AUDITOR)
    _membership(auditor, org, UserRole.REGULATOR_AUDITOR)
    resp = _client(auditor).get(reverse("monitoring-metrics"))
    assert resp.status_code == status.HTTP_200_OK
    assert "results" in resp.data


def test_dispute_analytics_forbidden_for_farmer(db):
    org = OrganizationFactory()
    farmer = UserFactory(role=UserRole.SMALLHOLDER_FARMER)
    _membership(farmer, org, UserRole.SMALLHOLDER_FARMER)
    FarmFactory(owner=farmer, organization=org)
    resp = _client(farmer).get(
        reverse("analytics-disputes-summary"),
        {"from": "2025-01-01", "to": "2025-12-31"},
    )
    assert resp.status_code == status.HTTP_403_FORBIDDEN


def test_dispute_analytics_ok_for_auditor(db):
    org = OrganizationFactory()
    auditor = UserFactory(role=UserRole.REGULATOR_AUDITOR)
    _membership(auditor, org, UserRole.REGULATOR_AUDITOR)
    resp = _client(auditor).get(
        reverse("analytics-disputes-summary"),
        {"from": "2025-01-01", "to": "2025-12-31"},
    )
    assert resp.status_code == status.HTTP_200_OK
    assert resp.data["organization_id"] == str(org.id)
    assert "volume_by_day" in resp.data


def test_document_detail_cross_tenant_blocked(db):
    org_a = OrganizationFactory()
    org_b = OrganizationFactory()
    farmer_a = UserFactory(role=UserRole.SMALLHOLDER_FARMER)
    farmer_b = UserFactory(role=UserRole.SMALLHOLDER_FARMER)
    _membership(farmer_a, org_a, UserRole.SMALLHOLDER_FARMER)
    _membership(farmer_b, org_b, UserRole.SMALLHOLDER_FARMER)
    FarmFactory(owner=farmer_a, organization=org_a)
    FarmFactory(owner=farmer_b, organization=org_b)
    doc = Document.objects.create(
        organization=org_a,
        uploaded_by=farmer_a,
        document_type=DocumentType.OTHER,
        title="A",
        file=SimpleUploadedFile("a.pdf", b"x", content_type="application/pdf"),
        file_name="a.pdf",
        sha256_hash="a" * 64,
        verification_state="HASHED",
    )
    resp = _client(farmer_b).get(reverse("document-detail", kwargs={"pk": doc.id}))
    assert resp.status_code == status.HTTP_404_NOT_FOUND
