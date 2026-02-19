from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIRequestFactory

from permissions.roles import (
    IsAdmin,
    IsCashier,
    IsPharmacist,
    IsPharmacistOrAdmin,
    IsReception,
    IsStaff,
)

User = get_user_model()


class PermissionRoleTests(TestCase):
    """
    Tests for role-based permissions.

    GUARANTEES:
    - Correct role access
    - No privilege escalation
    - Anonymous users denied everywhere
    """

    def setUp(self):
        self.factory = APIRequestFactory()

        self.admin = User.objects.create_user(
            email="admin@example.com",
            password="pass",
            role="admin",
        )
        self.pharmacist = User.objects.create_user(
            email="pharmacist@example.com",
            password="pass",
            role="pharmacist",
        )
        self.cashier = User.objects.create_user(
            email="cashier@example.com",
            password="pass",
            role="cashier",
        )
        self.reception = User.objects.create_user(
            email="reception@example.com",
            password="pass",
            role="reception",
        )

    # --------------------------------------------------
    # Helpers
    # --------------------------------------------------

    def _request_for(self, user=None):
        request = self.factory.get("/")
        request.user = user
        return request

    # --------------------------------------------------
    # ADMIN
    # --------------------------------------------------

    def test_admin_permissions(self):
        request = self._request_for(self.admin)

        self.assertTrue(IsAdmin().has_permission(request, None))
        self.assertTrue(IsStaff().has_permission(request, None))
        self.assertTrue(IsPharmacistOrAdmin().has_permission(request, None))

    # --------------------------------------------------
    # PHARMACIST
    # --------------------------------------------------

    def test_pharmacist_permissions(self):
        request = self._request_for(self.pharmacist)

        self.assertTrue(IsPharmacist().has_permission(request, None))
        self.assertTrue(IsStaff().has_permission(request, None))
        self.assertTrue(IsPharmacistOrAdmin().has_permission(request, None))

        self.assertFalse(IsAdmin().has_permission(request, None))
        self.assertFalse(IsCashier().has_permission(request, None))

    # --------------------------------------------------
    # CASHIER
    # --------------------------------------------------

    def test_cashier_permissions(self):
        request = self._request_for(self.cashier)

        self.assertTrue(IsCashier().has_permission(request, None))
        self.assertTrue(IsStaff().has_permission(request, None))

        self.assertFalse(IsAdmin().has_permission(request, None))
        self.assertFalse(IsPharmacist().has_permission(request, None))
        self.assertFalse(IsPharmacistOrAdmin().has_permission(request, None))

    # --------------------------------------------------
    # RECEPTION
    # --------------------------------------------------

    def test_reception_permissions(self):
        request = self._request_for(self.reception)

        self.assertTrue(IsReception().has_permission(request, None))
        self.assertTrue(IsStaff().has_permission(request, None))

        self.assertFalse(IsAdmin().has_permission(request, None))
        self.assertFalse(IsPharmacistOrAdmin().has_permission(request, None))

    # --------------------------------------------------
    # ANONYMOUS
    # --------------------------------------------------

    def test_anonymous_user_denied_everywhere(self):
        request = self._request_for(None)

        self.assertFalse(IsAdmin().has_permission(request, None))
        self.assertFalse(IsPharmacist().has_permission(request, None))
        self.assertFalse(IsCashier().has_permission(request, None))
        self.assertFalse(IsReception().has_permission(request, None))
        self.assertFalse(IsStaff().has_permission(request, None))
        self.assertFalse(IsPharmacistOrAdmin().has_permission(request, None))
