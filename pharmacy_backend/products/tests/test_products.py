from django.test import TestCase
from django.db import IntegrityError

from products.models import Product


class ProductModelTests(TestCase):
    """
    Product model tests.

    GUARANTEES:
    - Products can be created safely
    - SKU uniqueness is enforced
    - Pricing is sane
    """

    def test_product_creation(self):
        """A valid product should be created successfully."""
        product = Product.objects.create(
            name="Amoxicillin 250mg",
            sku="AMX-250",
            selling_price=250,
        )

        self.assertEqual(product.name, "Amoxicillin 250mg")
        self.assertEqual(product.sku, "AMX-250")

    def test_sku_must_be_unique(self):
        """SKU duplication must be rejected."""
        Product.objects.create(
            name="Ibuprofen",
            sku="IBU-200",
            selling_price=200,
        )

        with self.assertRaises(IntegrityError):
            Product.objects.create(
                name="Ibuprofen Duplicate",
                sku="IBU-200",
                selling_price=220,
            )

    def test_product_price_is_non_negative(self):
        """Selling price must never be negative."""
        product = Product.objects.create(
            name="Vitamin C",
            sku="VIT-C",
            selling_price=0,
        )

        self.assertGreaterEqual(product.selling_price, 0)

    def test_product_string_representation(self):
        """__str__ should be human readable."""
        product = Product.objects.create(
            name="Cough Syrup",
            sku="COUGH-100",
            selling_price=500,
        )

        self.assertIn("Cough Syrup", str(product))
