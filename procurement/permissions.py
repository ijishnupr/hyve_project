"""Role-based DRF permission classes."""
from rest_framework.permissions import SAFE_METHODS, BasePermission


class IsProcurementManagerOrReadOnly(BasePermission):
    """Read for any authenticated user; writes for procurement managers/admins."""

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return bool(request.user and request.user.is_authenticated)
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.can_manage_procurement
        )


class CanApprove(BasePermission):
    """Object-level / action permission for approval endpoints."""

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.can_approve
        )


class CanManageBills(BasePermission):
    """Read for any authenticated user; writes for accountants/admins."""

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return bool(request.user and request.user.is_authenticated)
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.can_manage_bills
        )
