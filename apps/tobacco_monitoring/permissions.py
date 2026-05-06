from rest_framework.permissions import BasePermission

from apps.common.enums import UserRole


class IsBuyerAdminOrAuditor(BasePermission):
    """Buyer operations, system admin, or regulator/auditor."""

    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in (
            UserRole.BUYER_CONTRACTOR,
            UserRole.SYSTEM_ADMIN,
            UserRole.REGULATOR_AUDITOR,
        )
