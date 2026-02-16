from rest_framework.permissions import BasePermission


class IsPharmacyStaff(BasePermission):
    """
    Allows access only to pharmacy staff roles.
    """

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated)
