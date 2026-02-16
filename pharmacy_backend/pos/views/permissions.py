from rest_framework.permissions import BasePermission


class IsPOSUser(BasePermission):
    """
    Allows access only to users permitted to operate the POS system.

    Allowed roles:
    - admin
    - pharmacist
    - cashier
    """

    allowed_roles = {
        "admin",
        "pharmacist",
        "cashier",
    }

    def has_permission(self, request, view):
        user = request.user

        if not user or not user.is_authenticated:
            return False

        return user.role in self.allowed_roles
