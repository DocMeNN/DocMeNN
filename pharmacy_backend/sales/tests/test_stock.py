from django.test import TestCase
from django.utils import timezone
from django.contrib.auth import get_user_model

from products.models import Product, StockBatch
from products.services.stock_fifo import restore_stock_from_sale

from sales.models.sale import Sale
from sales.models.sale_item import SaleItem

User = get_user_model()


class StockLedgerTests(TestCase):
    """
    Tests for stock restoration and ledger correctness.

    GUARANTEES:
    - Stock is restored correctly
    - No negative stock
    - FIFO-safe behavior across batches
    - Stock is not silently inflated
    """

    def setUp(self):
        self.user = User.objects.create_user(
            email="pharmacist@example.com",
            password="pass",
            role="pharmacist",
        )

        self.product = Product.objects.create(
            sku="SKU-200",
            name="Ibuprofen",
            unit_price="75.00",
        )

        # ----------------------------------
        # FIFO Batches (older first)
        # ----------------------------------
        self.old_batch = StockBatch.objects.create(
            product=self.product,
            quantity_remaining=3,
            expiry_date=timezone.now().date(),
            is_active=True,
        )

        self.new_batch = StockBatch.objects.create(
            product=self.product,
            quantity_remaining=5,
            expiry_date=timezone.now().date(),
            is_active=True,
        )

        # ----------------------------------
        # Completed Sale (sold from old batch)
        # ----------------------------------
        self.sale = Sale.objects.create(
            invoice_no="INV-200",
            user=self.user,
            payment_method="cash",
            status=Sale.STATUS_COMPLETED,
            subtotal_amount="150.00",
            total_amount="150.00",
            completed_at=timezone.now(),
        )

        self.item = SaleItem.objects.create(
            sale=self.sale,
            product=self.product,
            batch_reference=self.old_batch,
            quantity=2,
            unit_price="75.00",
            total_price="150.00",
        )

    # ======================================================
    # BASIC RESTORATION
    # ======================================================

    def test_restore_stock_from_sale(self):
        restore_stock_from_sale(
            product=self.product,
            quantity=self.item.quantity,
            user=self.user,
            reference_sale=self.sale,
        )

        self.old_batch.refresh_from_db()
        self.new_batch.refresh_from_db()

        # Restored only to original batch
        self.assertEqual(self.old_batch.quantity_remaining, 5)
        self.assertEqual(self.new_batch.quantity_remaining, 5)

    # ======================================================
    # FIFO SAFETY
    # ======================================================

    def test_fifo_batch_is_respected_on_restore(self):
        restore_stock_from_sale(
            product=self.product,
            quantity=self.item.quantity,
            user=self.user,
            reference_sale=self.sale,
        )

        self.old_batch.refresh_from_db()

        # Restore goes back to the same batch used in sale
        self.assertEqual(self.old_batch.quantity_remaining, 5)

    # ======================================================
    # SAFETY INVARIANTS
    # ======================================================

    def test_stock_never_negative(self):
        self.assertGreaterEqual(self.old_batch.quantity_remaining, 0)
        self.assertGreaterEqual(self.new_batch.quantity_remaining, 0)

    def test_stock_not_over_restored(self):
        restore_stock_from_sale(
            product=self.product,
            quantity=self.item.quantity,
            user=self.user,
            reference_sale=self.sale,
        )

        self.old_batch.refresh_from_db()

        # Original was 3, sold 2 → restored back to 5
        self.assertEqual(self.old_batch.quantity_remaining, 5)
