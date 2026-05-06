"""
Single source of truth for object-level access (RBAC + tenant).
All AI tools, forecasting, and anomaly endpoints must use these checks.
"""
from __future__ import annotations

import uuid

from django.db.models import Q

from apps.common.enums import UserRole
from apps.common.org_utils import get_user_primary_organization
from apps.disputes.models import Dispute
from apps.documents.models import Document
from apps.farms.models import Farm
from apps.lots.models import Lot
from apps.organizations.models import BuyerLotAssignment
from apps.sales.models import Sale
from apps.settlements.models import Settlement


def _org_id(user) -> uuid.UUID | None:
    org = get_user_primary_organization(user)
    return org.id if org else None


def _farm_org_id(farm: Farm) -> uuid.UUID | None:
    return farm.organization_id


def _lot_org_id(lot: Lot) -> uuid.UUID | None:
    return lot.farm.organization_id


def buyer_assigned_lot_ids(user, org_id: uuid.UUID) -> set[uuid.UUID]:
    """Lots explicitly assigned to this buyer within the org."""
    return set(
        BuyerLotAssignment.objects.filter(buyer=user, organization_id=org_id).values_list(
            "lot_id", flat=True
        )
    )


def buyer_lot_ids_via_sales(user, org_id: uuid.UUID) -> set[uuid.UUID]:
    """Lots where this user is the recorded buyer on a sale, scoped by org."""
    return set(
        Sale.objects.filter(buyer=user, lot__farm__organization_id=org_id).values_list(
            "lot_id", flat=True
        )
    )


def buyer_accessible_lot_ids(user, org_id: uuid.UUID) -> set[uuid.UUID]:
    return buyer_assigned_lot_ids(user, org_id) | buyer_lot_ids_via_sales(user, org_id)


def is_auditor_or_admin(user) -> bool:
    return user.role in (UserRole.REGULATOR_AUDITOR, UserRole.SYSTEM_ADMIN)


def is_system_admin(user) -> bool:
    return user.role == UserRole.SYSTEM_ADMIN


def can_view_farm(user, farm: Farm) -> bool:
    oid = _org_id(user)
    if oid is None:
        return False
    if _farm_org_id(farm) != oid:
        return False
    if user.is_superuser:
        return True
    if user.role == UserRole.SMALLHOLDER_FARMER:
        return farm.owner_id == user.id
    if user.role == UserRole.BUYER_CONTRACTOR:
        return Lot.objects.filter(
            farm_id=farm.id,
            id__in=buyer_accessible_lot_ids(user, oid),
        ).exists()
    if user.role in (UserRole.REGULATOR_AUDITOR, UserRole.SYSTEM_ADMIN):
        return True
    return False


def can_view_lot(user, lot: Lot) -> bool:
    oid = _org_id(user)
    if oid is None:
        return False
    if _lot_org_id(lot) != oid:
        return False
    if user.is_superuser:
        return True
    farm = lot.farm
    if user.role == UserRole.SMALLHOLDER_FARMER:
        return farm.owner_id == user.id
    if user.role == UserRole.BUYER_CONTRACTOR:
        return lot.id in buyer_accessible_lot_ids(user, oid)
    if user.role in (UserRole.REGULATOR_AUDITOR, UserRole.SYSTEM_ADMIN):
        return True
    return False


def can_attach_document_to_lot(user, lot: Lot) -> bool:
    """Whether the user may upload a document linked to this lot (write scope aligned with org tenancy)."""
    if user.role == UserRole.SMALLHOLDER_FARMER:
        return lot.farm.owner_id == user.id
    if user.role == UserRole.BUYER_CONTRACTOR:
        org_ids = user.memberships.filter(is_active=True).values_list(
            "organization_id", flat=True
        )
        return lot.farm.organization_id in org_ids
    if user.role in (UserRole.REGULATOR_AUDITOR, UserRole.SYSTEM_ADMIN):
        return can_view_lot(user, lot)
    return False


def can_view_document(user, document: Document) -> bool:
    if not document.lot_id:
        if user.role == UserRole.SMALLHOLDER_FARMER:
            return document.uploaded_by_id == user.id
        return is_auditor_or_admin(user) and _org_id(user) is not None
    try:
        lot = document.lot
    except Lot.DoesNotExist:
        return False
    return can_view_lot(user, lot)


def can_view_settlement(user, settlement: Settlement) -> bool:
    oid = _org_id(user)
    if oid is None:
        return False
    lot = settlement.sale.lot
    if _lot_org_id(lot) != oid:
        return False
    if user.is_superuser:
        return True
    if user.role == UserRole.SMALLHOLDER_FARMER:
        return settlement.farmer_id == user.id or lot.farm.owner_id == user.id
    if user.role == UserRole.BUYER_CONTRACTOR:
        return settlement.created_by_id == user.id or settlement.sale.buyer_id == user.id
    if user.role in (UserRole.REGULATOR_AUDITOR, UserRole.SYSTEM_ADMIN):
        return True
    return False


def can_view_dispute(user, dispute: Dispute) -> bool:
    oid = _org_id(user)
    if oid is None:
        return False
    if dispute.organization_id and dispute.organization_id != oid:
        return False
    if dispute.lot_id:
        if _lot_org_id(dispute.lot) != oid:
            return False
        return can_view_lot(user, dispute.lot) or dispute.raised_by_id == user.id
    if dispute.sale_id:
        lot = dispute.sale.lot
        if _lot_org_id(lot) != oid:
            return False
        return can_view_lot(user, lot) or dispute.raised_by_id == user.id
    return is_auditor_or_admin(user)


def lots_queryset_for_user(user):
    """Tenant-scoped base queryset for lots with role filter."""
    oid = _org_id(user)
    if oid is None:
        return Lot.objects.none()
    qs = Lot.objects.filter(farm__organization_id=oid)
    if user.is_superuser:
        return qs
    if user.role == UserRole.SMALLHOLDER_FARMER:
        return qs.filter(farm__owner=user)
    if user.role == UserRole.BUYER_CONTRACTOR:
        ids = buyer_accessible_lot_ids(user, oid)
        return qs.filter(Q(id__in=ids) | Q(sales__buyer=user)).distinct()
    if user.role in (UserRole.REGULATOR_AUDITOR, UserRole.SYSTEM_ADMIN):
        return qs
    return Lot.objects.none()


def can_view_anomaly_alert(user, alert) -> bool:
    """Alert rows are tenant-scoped; subjects must pass object-level rules."""
    from apps.ai_intelligence.models import AnomalyAlert

    if not isinstance(alert, AnomalyAlert):
        return False
    oid = _org_id(user)
    if oid is None or alert.organization_id != oid:
        return False
    if user.is_superuser:
        return True
    if alert.lot_id:
        return can_view_lot(user, alert.lot)
    if alert.farm_id:
        return can_view_farm(user, alert.farm)
    if alert.document_id:
        return can_view_document(user, alert.document)
    if alert.settlement_id:
        return can_view_settlement(user, alert.settlement)
    if is_auditor_or_admin(user):
        return True
    return False


def farms_queryset_for_user(user):
    oid = _org_id(user)
    if oid is None:
        return Farm.objects.none()
    qs = Farm.objects.filter(organization_id=oid)
    if user.is_superuser:
        return qs
    if user.role == UserRole.SMALLHOLDER_FARMER:
        return qs.filter(owner=user)
    if user.role == UserRole.BUYER_CONTRACTOR:
        lot_ids = buyer_accessible_lot_ids(user, oid)
        return qs.filter(lots__id__in=lot_ids).distinct()
    if user.role in (UserRole.REGULATOR_AUDITOR, UserRole.SYSTEM_ADMIN):
        return qs
    return Farm.objects.none()
