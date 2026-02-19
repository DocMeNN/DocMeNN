# sales/tests/test_stock.py

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from products.models import Product, StockBatch
from products.models.stock_movement import StockMovement
from products.services.stock_fifo import deduct_stock_fifo, restore_stock_from_sale
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
            unit_price=Decimal("75.00"),
            is_active=True,
        )

        # ----------------------------------
        # FIFO Batches (older first)
        # ----------------------------------
        today = timezone.now().date()

        self.old_batch = StockBatch.objects.create(
            product=self.product,
            batch_number="OLD-BATCH",
            quantity_received=3,
            quantity_remaining=3,
            unit_cost=Decimal("40.00"),
            expiry_date=today,
            is_active=True,
        )

        self.new_batch = StockBatch.objects.create(
            product=self.product,
            batch_number="NEW-BATCH",
            quantity_received=5,
            quantity_remaining=5,
            unit_cost=Decimal("45.00"),
            expiry_date=today,
            is_active=True,
        )

        # ----------------------------------
        # Completed Sale (2 units)
        # ----------------------------------
        self.sale = Sale.objects.create(
            invoice_no="INV-200",
            user=self.user,
            payment_method="cash",
            status=Sale.STATUS_COMPLETED,
            subtotal_amount=Decimal("150.00"),
            total_amount=Decimal("150.00"),
            completed_at=timezone.now(),
        )

        self.item = SaleItem.objects.create(
            sale=self.sale,
            product=self.product,
            batch_reference=self.old_batch,
            quantity=2,
            unit_price=Decimal("75.00"),
            total_price=Decimal("150.00"),
        )

        # -------------------------------------------------------
        # Critical: create SALE stock movements (ledger history)
        # The restore service restores using StockMovement history.
        # -------------------------------------------------------
        deduct_stock_fifo(
            product=self.product,
            quantity=self.item.quantity,
            user=self.user,
            sale=self.sale,
            store=None,  # single-store test mode
        )

    # ======================================================
    # BASIC RESTORATION
    # ======================================================

    def test_restore_stock_from_sale(self):
        restored = restore_stock_from_sale(
            sale=self.sale,
            user=self.user,
            items=None,  # full restore
        )

        self.assertTrue(restored)

        self.old_batch.refresh_from_db()
        self.new_batch.refresh_from_db()

        # Original old batch: 3, sold 2 -> remaining 1
        # After restore, it returns to 3
        self.assertEqual(int(self.old_batch.quantity_remaining), 3)

        # New batch untouched
        self.assertEqual(int(self.new_batch.quantity_remaining), 5)

    # ======================================================
    # FIFO SAFETY
    # ======================================================

    def test_fifo_batch_is_respected_on_restore(self):
        restore_stock_from_sale(
            sale=self.sale,
            user=self.user,
            items=None,
        )

        # Refund movements must reference the same batch used in sale deduction
        refund_mvs = StockMovement.objects.filter(
            sale=self.sale,
            reason=StockMovement.Reason.REFUND,
            movement_type=StockMovement.MovementType.IN,
            batch=self.old_batch,
        )
        self.assertGreater(refund_mvs.count(), 0)

        self.old_batch.refresh_from_db()
        self.assertEqual(int(self.old_batch.quantity_remaining), 3)

    # ======================================================
    # SAFETY INVARIANTS
    # ======================================================

    def test_stock_never_negative(self):
        self.old_batch.refresh_from_db()
        self.new_batch.refresh_from_db()

        self.assertGreaterEqual(int(self.old_batch.quantity_remaining), 0)
        self.assertGreaterEqual(int(self.new_batch.quantity_remaining), 0)

    def test_stock_not_over_restored(self):
        # First restore OK
        restore_stock_from_sale(sale=self.sale, user=self.user, items=None)

        self.old_batch.refresh_from_db()
        self.assertEqual(int(self.old_batch.quantity_remaining), 3)

        # Second restore should fail (nothing refundable left)
        with self.assertRaises(Exception):
            restore_stock_from_sale(sale=self.sale, user=self.user, items=None)
