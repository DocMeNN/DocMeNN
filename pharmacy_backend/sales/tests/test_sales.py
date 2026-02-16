from django.test import TestCase
from django.utils import timezone
from django.contrib.auth import get_user_model

from sales.models.sale import Sale
from sales.models.sale_item import SaleItem
from sales.services.sale_lifecycle import (
    validate_transition,
    InvalidSaleTransitionError,
)

from products.models import Product, StockBatch

User = get_user_model()


class SaleModelTests(TestCase):
    """
    Tests for Sale lifecycle and immutability.

    GUARANTEES:
    - Sale totals are preserved after completion
    - Sale state transitions obey domain rules
    - Illegal transitions are blocked
    """

    def setUp(self):
        self.user = User.objects.create_user(
            email="cashier@example.com",
            password="pass",
            role="cashier",
        )

        self.product = Product.objects.create(
            sku="SKU-100",
            name="Paracetamol",
            unit_price="50.00",
        )

        self.batch = StockBatch.objects.create(
            product=self.product,
            quantity_remaining=20,
            expiry_date=timezone.now().date(),
            is_active=True,
        )

        self.sale = Sale.objects.create(
            invoice_no="INV-100",
            user=self.user,
            payment_method="cash",
            status=Sale.STATUS_COMPLETED,
            subtotal_amount="100.00",
            total_amount="100.00",
            completed_at=timezone.now(),
        )

        SaleItem.objects.create(
            sale=self.sale,
            product=self.product,
            batch_reference=self.batch,
            quantity=2,
            unit_price="50.00",
            total_price="100.00",
        )

    # =====================================================
    # IMMUTABILITY TESTS
    # =====================================================

    def test_sale_totals_are_immutable_after_completion(self):
        """
        Business rule:
        Financial totals must not change after completion.
        """
        self.sale.subtotal_amount = "999.00"
        self.sale.total_amount = "999.00"
        self.sale.save()

        refreshed = Sale.objects.get(id=self.sale.id)

        self.assertEqual(str(refreshed.subtotal_amount), "100.00")
        self.assertEqual(str(refreshed.total_amount), "100.00")

    def test_completed_sale_has_timestamp(self):
        self.assertIsNotNone(self.sale.completed_at)

    def test_sale_has_items(self):
        self.assertEqual(self.sale.items.count(), 1)

    # =====================================================
    # LIFECYCLE TRANSITION TESTS
    # =====================================================

    def test_completed_sale_can_transition_to_refunded(self):
        """
        Valid transition:
        COMPLETED → REFUNDED
        """
        try:
            validate_transition(
                sale=self.sale,
                target_status=Sale.STATUS_REFUNDED,
            )
        except InvalidSaleTransitionError:
            self.fail("Valid transition raised InvalidSaleTransitionError")

    def test_completed_sale_cannot_transition_to_completed_again(self):
        """
        Illegal transition:
        COMPLETED → COMPLETED
        """
        with self.assertRaises(InvalidSaleTransitionError):
            validate_transition(
                sale=self.sale,
                target_status=Sale.STATUS_COMPLETED,
            )

    def test_refunded_sale_is_terminal(self):
        """
        Terminal state rule:
        REFUNDED sales cannot transition further.
        """
        self.sale.status = Sale.STATUS_REFUNDED
        self.sale.save()

        with self.assertRaises(InvalidSaleTransitionError):
            validate_transition(
                sale=self.sale,
                target_status=Sale.STATUS_COMPLETED,
            )
