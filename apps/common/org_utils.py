"""Resolve the active organization (tenant) for a user."""

from __future__ import annotations

from apps.organizations.models import Organization, OrganizationMembership


def get_user_primary_organization(user) -> Organization | None:
    """
    Primary membership first, then most recent active membership.
    If none, fall back to an owned farm's organization (legacy / dev tests).
    """
    if not user or not user.is_authenticated:
        return None
    qs = (
        OrganizationMembership.objects.filter(user=user, is_active=True)
        .select_related("organization")
        .order_by("-is_primary", "-created_at")
    )
    m = qs.first()
    if m:
        return m.organization
    from apps.farms.models import Farm

    farm = Farm.objects.filter(owner=user).exclude(organization__isnull=True).select_related("organization").first()
    return farm.organization if farm else None


def require_organization(user) -> Organization:
    from django.core.exceptions import PermissionDenied

    org = get_user_primary_organization(user)
    if org is None:
        raise PermissionDenied("No active organization membership.")
    return org
