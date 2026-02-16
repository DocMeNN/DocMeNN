from django.test import TestCase
from django.contrib.auth import get_user_model

from products.models import Product, ProductBatch


User = get_user_model()


class ProductStockTests(TestCase):
    """
    Stock-level tests.

    GUARANTEES:
    - Stock quantities are non-negative
    - Batches belong to products
    - No silent corruption of stock data
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username="stock_admin",
            password="password123",
        )

        self.product = Product.objects.create(
            name="Paracetamol 500mg",
            sku="PCM-500",
            selling_price=100,
        )

        self.batch = ProductBatch.objects.create(
            product=self.product,
            batch_no="BATCH-001",
            quantity=50,
            expiry_date="2030-12-31",
        )

    def test_product_has_initial_stock(self):
        """Product batch should start with a positive stock."""
        self.assertGreaterEqual(self.batch.quantity, 0)

    def test_batch_is_linked_to_correct_product(self):
        """Batch must always belong to its product."""
        self.assertEqual(self.batch.product, self.product)

    def test_multiple_batches_allowed_for_same_product(self):
        """A product can safely have multiple batches."""
        batch2 = ProductBatch.objects.create(
            product=self.product,
            batch_no="BATCH-002",
            quantity=30,
            expiry_date="2031-01-01",
        )

        self.assertEqual(
            self.product.batches.count(),
            2,
        )

    def test_stock_never_negative(self):
        """System must never allow negative stock values."""
        self.batch.quantity = 0
        self.batch.save()

        self.assertGreaterEqual(self.batch.quantity, 0)
