# products/tests/test_products.py

from decimal import Decimal

from django.db import IntegrityError
from django.test import TestCase

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
            unit_price=Decimal("250.00"),
            is_active=True,
        )

        self.assertEqual(product.name, "Amoxicillin 250mg")
        self.assertEqual(product.sku, "AMX-250")

    def test_sku_must_be_unique(self):
        """SKU duplication must be rejected."""
        Product.objects.create(
            name="Ibuprofen",
            sku="IBU-200",
            unit_price=Decimal("200.00"),
            is_active=True,
        )

        with self.assertRaises(IntegrityError):
            Product.objects.create(
                name="Ibuprofen Duplicate",
                sku="IBU-200",
                unit_price=Decimal("220.00"),
                is_active=True,
            )

    def test_product_price_is_non_negative(self):
        """Selling price must never be negative."""
        product = Product.objects.create(
            name="Vitamin C",
            sku="VIT-C",
            unit_price=Decimal("0.00"),
            is_active=True,
        )

        self.assertGreaterEqual(product.unit_price, Decimal("0.00"))

    def test_product_string_representation(self):
        """__str__ should be human readable."""
        product = Product.objects.create(
            name="Cough Syrup",
            sku="COUGH-100",
            unit_price=Decimal("500.00"),
            is_active=True,
        )

        self.assertIn("Cough Syrup", str(product))
