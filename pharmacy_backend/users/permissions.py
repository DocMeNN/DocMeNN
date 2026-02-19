# users/permissions.py

from rest_framework.permissions import BasePermission


# ---------------- BASE ROLE PERMISSION ----------------
class HasRole(BasePermission):
    """
    Base permission to check user role safely.
    """

    allowed_roles = set()

    def has_permission(self, request, view):
        user = request.user
        return user and user.is_authenticated and user.role in self.allowed_roles


# ---------------- ROLE PERMISSIONS ----------------
class IsAdmin(HasRole):
    allowed_roles = {"admin"}


class IsPharmacist(HasRole):
    allowed_roles = {"pharmacist"}


class IsCashier(HasRole):
    allowed_roles = {"cashier"}


class IsReception(HasRole):
    allowed_roles = {"reception"}


class IsStaff(HasRole):
    """
    Any staff member:
    - admin
    - pharmacist
    - cashier
    - reception
    """

    allowed_roles = {"admin", "pharmacist", "cashier", "reception"}


class IsPharmacistOrAdmin(HasRole):
    allowed_roles = {"admin", "pharmacist"}
