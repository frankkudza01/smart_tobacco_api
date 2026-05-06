"""Query scoping: which farms / polygons a user may access."""

from __future__ import annotations

from django.db.models import QuerySet

from apps.common.enums import UserRole
from apps.farms.models import Farm
from apps.tobacco_monitoring.models import TobaccoFieldPolygon


def farms_visible_for_user(user) -> QuerySet[Farm]:
    if not user.is_authenticated:
        return Farm.objects.none()
    role = getattr(user, "role", None)
    if role == UserRole.SMALLHOLDER_FARMER:
        return Farm.objects.filter(owner=user)
    if role == UserRole.BUYER_CONTRACTOR:
        org_ids = user.memberships.values_list("organization_id", flat=True)
        return Farm.objects.filter(organization_id__in=org_ids)
    if role in (UserRole.SYSTEM_ADMIN, UserRole.REGULATOR_AUDITOR):
        return Farm.objects.all()
    return Farm.objects.none()


def polygons_visible_for_user(user) -> QuerySet[TobaccoFieldPolygon]:
    farm_ids = farms_visible_for_user(user).values_list("id", flat=True)
    return TobaccoFieldPolygon.objects.filter(farm_id__in=farm_ids)
