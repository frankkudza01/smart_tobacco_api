from rest_framework.permissions import BasePermission

from apps.common.enums import UserRole


class IsSmallholderFarmer(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.role == UserRole.SMALLHOLDER_FARMER
        )


class IsBuyerContractor(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.role == UserRole.BUYER_CONTRACTOR
        )


class IsRegulatorAuditor(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.role == UserRole.REGULATOR_AUDITOR
        )


class IsSystemAdmin(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.role == UserRole.SYSTEM_ADMIN
        )


class IsFarmerOrBuyer(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in (
            UserRole.SMALLHOLDER_FARMER,
            UserRole.BUYER_CONTRACTOR,
        )


class CanRunFarmProvenanceChecks(BasePermission):
    """
    Who may POST farm-level provenance / sync / document checks.
    Object access (which farm) is enforced in services via can_view_farm.
    """

    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in (
            UserRole.SMALLHOLDER_FARMER,
            UserRole.BUYER_CONTRACTOR,
            UserRole.REGULATOR_AUDITOR,
            UserRole.SYSTEM_ADMIN,
        )


class IsAdminOrAuditor(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in (
            UserRole.SYSTEM_ADMIN,
            UserRole.REGULATOR_AUDITOR,
        )


class ReadOnly(BasePermission):
    def has_permission(self, request, view):
        return request.method in ("GET", "HEAD", "OPTIONS")
