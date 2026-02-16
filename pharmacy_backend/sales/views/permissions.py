# sales/views/permissions.py

from rest_framework.permissions import BasePermission


class CanRefundSale(BasePermission):
    """
    Refund authorization rule.

    POLICY:
    - Only pharmacists or admins can refund sales
    - Read permissions are irrelevant here (POST-only endpoint)

    Assumes:
    - User model has `role` field
    """

    allowed_roles = {"pharmacist", "admin"}

    def has_permission(self, request, view):
        user = request.user

        if not user or not user.is_authenticated:
            return False

        return getattr(user, "role", None) in self.allowed_roles

