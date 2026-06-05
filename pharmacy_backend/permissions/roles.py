from rest_framework.permissions import BasePermission


# -------------------------------------------------
# Pharmacist OR Admin
# -------------------------------------------------
class IsPharmacistOrAdmin(BasePermission):
    """
    Inventory actions:
    - Create
    - Update
    Allowed for: Pharmacist OR Admin
    """

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role in ["pharmacist", "admin"]
        )


# -------------------------------------------------
# Admin Only
# -------------------------------------------------
class IsAdmin(BasePermission):
    """
    Dangerous / irreversible actions
    - Delete
    - System configuration
    """

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role == "admin"
        )


# -------------------------------------------------
# Pharmacist Only
# -------------------------------------------------
class IsPharmacist(BasePermission):
    """
    Pharmacy operations
    """

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role == "pharmacist"
        )


# -------------------------------------------------
# Cashier Only
# -------------------------------------------------
class IsCashier(BasePermission):
    """
    POS operations
    """

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role == "cashier"
        )


# -------------------------------------------------
# Reception Only
# -------------------------------------------------
class IsReception(BasePermission):
    """
    Patient registration & appointments
    """

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role == "reception"
        )


# -------------------------------------------------
# Any Staff (NOT Customer)
# -------------------------------------------------
class IsStaff(BasePermission):
    """
    Admin + Pharmacist + Cashier + Reception
    """

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role in [
                "admin",
                "pharmacist",
                "cashier",
                "reception",
            ]
        )
