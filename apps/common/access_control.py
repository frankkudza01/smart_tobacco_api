"""
Central RBAC + tenant exports. Never trust client-supplied org_id — derive from JWT via org_utils.
"""
from __future__ import annotations

# Re-export the canonical access layer (single source of truth).
from apps.common.access import (  # noqa: F401
    buyer_accessible_lot_ids,
    can_view_anomaly_alert,
    can_view_dispute,
    can_view_document,
    can_view_farm,
    can_view_lot,
    can_view_settlement,
    farms_queryset_for_user,
    is_auditor_or_admin,
    is_system_admin,
    lots_queryset_for_user,
)
from apps.common.org_utils import get_user_primary_organization, require_organization  # noqa: F401


def documents_queryset_for_org(user):
    """Documents scoped to the user's primary organization (denormalized on Document)."""
    from apps.documents.models import Document

    org = get_user_primary_organization(user)
    if org is None:
        return Document.objects.none()
    return Document.objects.filter(organization_id=org.id).select_related("lot", "uploaded_by")


def disputes_queryset_for_org(user):
    from apps.disputes.models import Dispute
    from django.db.models import Q

    from apps.common.enums import UserRole

    org = get_user_primary_organization(user)
    if org is None:
        return Dispute.objects.none()
    qs = Dispute.objects.filter(organization_id=org.id).select_related(
        "raised_by", "lot", "sale", "resolved_by"
    ).prefetch_related("comments")
    if user.is_superuser:
        return qs
    if user.role == UserRole.SMALLHOLDER_FARMER:
        return qs.filter(raised_by=user)
    if user.role == UserRole.BUYER_CONTRACTOR:
        lot_ids = lots_queryset_for_user(user).values_list("id", flat=True)
        return qs.filter(
            Q(assigned_to=user) | Q(sale__buyer=user) | Q(lot_id__in=lot_ids)
        ).distinct()
    if user.role in (UserRole.REGULATOR_AUDITOR, UserRole.SYSTEM_ADMIN):
        return qs
    return Dispute.objects.none()
