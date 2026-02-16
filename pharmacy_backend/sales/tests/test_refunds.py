from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone

from rest_framework.test import APIClient
from rest_framework import status

from sales.models.sale import Sale
from sales.models.sale_item import SaleItem
from sales.models.refund_audit import RefundAudit

from products.models import Product, StockBatch

User = get_user_model()


class SaleRefundAPITests(TestCase):
    """
    Refund flow integration tests.

    GUARANTEES:
    - Refund endpoint works end-to-end
    - Authorization is enforced
    - Audit is created exactly once
    - Stock is restored atomically
    - Invalid states are blocked
    """

    def setUp(self):
        self.client = APIClient()

        # ----------------------------------
        # Users
        # ----------------------------------
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

        # ----------------------------------
        # Product & Stock
        # ----------------------------------
        self.product = Product.objects.create(
            sku="SKU-001",
            name="Amoxicillin",
            unit_price="100.00",
        )

        self.batch = StockBatch.objects.create(
            product=self.product,
            quantity_remaining=10,
            expiry_date=timezone.now().date(),
            is_active=True,
        )

        # ----------------------------------
        # Completed Sale
        # ----------------------------------
        self.sale = Sale.objects.create(
            invoice_no="INV-001",
            user=self.pharmacist,
            payment_method="cash",
            status=Sale.STATUS_COMPLETED,
            subtotal_amount="200.00",
            total_amount="200.00",
            completed_at=timezone.now(),
        )

        SaleItem.objects.create(
            sale=self.sale,
            product=self.product,
            batch_reference=self.batch,
            quantity=2,
            unit_price="100.00",
            total_price="200.00",
        )

        self.refund_url = (
            reverse("sales-detail", args=[self.sale.id]) + "refund/"
        )

    # ======================================================
    # SUCCESS CASE
    # ======================================================

    def test_pharmacist_can_refund_sale_successfully(self):
        self.client.force_authenticate(self.pharmacist)

        response = self.client.post(
            self.refund_url,
            {"reason": "Customer returned item"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.sale.refresh_from_db()
        self.batch.refresh_from_db()

        # Sale state updated
        self.assertEqual(self.sale.status, Sale.STATUS_REFUNDED)

        # Audit created exactly once
        self.assertEqual(
            RefundAudit.objects.filter(sale=self.sale).count(),
            1,
        )

        # Stock restored
        self.assertEqual(self.batch.quantity_remaining, 12)

    # ======================================================
    # AUTHORIZATION
    # ======================================================

    def test_cashier_cannot_refund_sale(self):
        self.client.force_authenticate(self.cashier)

        response = self.client.post(self.refund_url, {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.sale.refresh_from_db()
        self.batch.refresh_from_db()

        # No mutation occurred
        self.assertEqual(self.sale.status, Sale.STATUS_COMPLETED)
        self.assertEqual(self.batch.quantity_remaining, 10)
        self.assertEqual(
            RefundAudit.objects.filter(sale=self.sale).count(),
            0,
        )

    def test_unauthenticated_user_cannot_refund_sale(self):
        response = self.client.post(self.refund_url, {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    # ======================================================
    # DUPLICATE REFUND BLOCKED
    # ======================================================

    def test_duplicate_refund_is_blocked(self):
        self.client.force_authenticate(self.pharmacist)

        RefundAudit.objects.create(
            sale=self.sale,
            refunded_by=self.pharmacist,
            original_total_amount=self.sale.total_amount,
        )

        response = self.client.post(self.refund_url, {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        self.sale.refresh_from_db()
        self.batch.refresh_from_db()

        # No further mutation
        self.assertEqual(self.sale.status, Sale.STATUS_COMPLETED)
        self.assertEqual(self.batch.quantity_remaining, 10)
        self.assertEqual(
            RefundAudit.objects.filter(sale=self.sale).count(),
            1,
        )

    # ======================================================
    # INVALID STATE BLOCKED
    # ======================================================

    def test_refund_fails_if_sale_not_completed(self):
        self.client.force_authenticate(self.pharmacist)

        self.sale.status = Sale.STATUS_REFUNDED
        self.sale.save(update_fields=["status"])

        response = self.client.post(self.refund_url, {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
