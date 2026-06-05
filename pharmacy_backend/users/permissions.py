# users/permissions.py
from rest_framework.permissions import BasePermission


class IsAdmin(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == "admin"


class IsPharmacist(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == "pharmacist"


class IsCashier(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == "cashier"


class IsReception(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == "reception"


class IsStaff(BasePermission):
    """
    Any staff: admin + pharmacist + cashier + reception
    """
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated and 
            request.user.role in {"admin", "pharmacist", "cashier", "reception"}
        )


class IsPharmacistOrAdmin(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated and 
            request.user.role in {"admin", "pharmacist"}
        )
