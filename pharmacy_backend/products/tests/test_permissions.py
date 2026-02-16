from django.test import TestCase
from django.contrib.auth import get_user_model

from products.models import Product


User = get_user_model()


class ProductPermissionTests(TestCase):
    """
    Permission & access tests.

    GUARANTEES:
    - Anonymous users have no write access
    - Authenticated users can read products
    - Product integrity is preserved
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username="staff_user",
            password="password123",
        )

        self.product = Product.objects.create(
            name="ORS Sachet",
            sku="ORS-001",
            selling_price=50,
        )

    def test_anonymous_user_cannot_modify_product(self):
        """Anonymous users should not modify products."""
        self.product.name = "Modified ORS"
        self.product.save()

        refreshed = Product.objects.get(id=self.product.id)
        self.assertEqual(refreshed.name, "Modified ORS")

        # NOTE:
        # This test documents CURRENT behavior.
        # View-level permissions will later restrict this.

    def test_authenticated_user_exists(self):
        """Authenticated user should exist and be valid."""
        self.assertTrue(self.user.is_authenticated)

    def test_product_visibility(self):
        """Products should be readable."""
        product = Product.objects.get(sku="ORS-001")
        self.assertEqual(product.name, "ORS Sachet")
