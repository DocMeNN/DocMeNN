# sales/tests/test_refunds.py

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from products.models import Product, StockBatch
from products.services.stock_fifo import deduct_stock_fifo
from sales.models.refund_audit import RefundAudit
from sales.models.sale import Sale
from sales.models.sale_item import SaleItem

User = get_user_model()


# -----------------------------
# Accounting seeding helpers
# -----------------------------


def _pick_choice_value(field):
    choices = getattr(field, "choices", None)
    if not choices:
        return None

    first = choices[0]
    # flat: [(value, label), ...]
    if (
        isinstance(first, (list, tuple))
        and len(first) == 2
        and not isinstance(first[1], (list, tuple))
    ):
        return first[0]
    # grouped: [(group, [(value,label), ...]), ...]
    if (
        isinstance(first, (list, tuple))
        and len(first) == 2
        and isinstance(first[1], (list, tuple))
    ):
        inner = first[1]
        if inner and isinstance(inner[0], (list, tuple)) and len(inner[0]) == 2:
            return inner[0][0]
    return None


def _default_for_field(field):
    from django.db import models

    choice_val = _pick_choice_value(field)
    if choice_val is not None:
        return choice_val

    if isinstance(field, models.BooleanField):
        return True
    if isinstance(
        field, (models.IntegerField, models.BigIntegerField, models.SmallIntegerField)
    ):
        return 1
    if isinstance(field, models.DecimalField):
        return Decimal("0.00")
    if isinstance(field, models.DateField) and not isinstance(
        field, models.DateTimeField
    ):
        return date.today()
    if isinstance(field, models.DateTimeField):
        return timezone.now()
    if isinstance(field, models.CharField):
        max_len = getattr(field, "max_length", 255) or 255
        return ("TEST" * 50)[:max_len]
    if isinstance(field, models.TextField):
        return "TEST"
    return None


def _create_active_chart_and_accounts():
    """
    Refund flow can touch accounting posting/reversal.
    Ensure there is exactly one active chart AND required accounts exist.
    """
    from accounting.models.chart import ChartOfAccounts

    chart = ChartOfAccounts.objects.filter(is_active=True).first()
    if chart is None:
        fields = {f.name: f for f in ChartOfAccounts._meta.fields}
        payload = {"is_active": True}

        if "code" in fields:
            payload["code"] = f"TEST-COA-{uuid.uuid4().hex[:6].upper()}"
        if "name" in fields:
            payload["name"] = "Test Chart of Accounts"

        for fname, field in fields.items():
            if fname in payload:
                continue
            if getattr(field, "primary_key", False) or getattr(
                field, "auto_created", False
            ):
                continue
            if hasattr(field, "has_default") and field.has_default():
                continue
            if getattr(field, "null", False):
                continue
            if field.is_relation and getattr(field, "many_to_one", False):
                continue

            val = _default_for_field(field)
            if val is not None:
                payload[fname] = val

        # Retry to satisfy any extra validation rules
        for _ in range(6):
            try:
                chart = ChartOfAccounts.objects.create(**payload)
                ChartOfAccounts.objects.exclude(id=chart.id).update(is_active=False)
                break
            except ValidationError as exc:
                msg = getattr(exc, "message_dict", {}) or {}
                if not msg:
                    raise
                for fn in msg.keys():
                    if fn in payload:
                        continue
                    if fn == "code":
                        payload["code"] = f"TEST-COA-{uuid.uuid4().hex[:6].upper()}"
                        continue
                    if fn == "name":
                        payload["name"] = "Test Chart of Accounts"
                        continue
                    field = fields.get(fn)
                    if field is None:
                        raise
                    val = _default_for_field(field)
                    if val is not None:
                        payload[fn] = val
                    else:
                        raise

        if chart is None:
            raise ValidationError(
                "Unable to create an active ChartOfAccounts for refund tests."
            )

    # Find “account inside chart” model: must have 'code' and FK to ChartOfAccounts
    AccountModel = None
    chart_fk_field = None
    for m in apps.get_models():
        field_names = {f.name for f in m._meta.fields}
        if "code" not in field_names:
            continue
        for f in m._meta.fields:
            if (
                f.is_relation
                and getattr(f, "many_to_one", False)
                and getattr(f.remote_field, "model", None) == chart.__class__
            ):
                AccountModel = m
                chart_fk_field = f.name
                break
        if AccountModel is not None:
            break

    if AccountModel is None:
        # If your project uses a different approach (seed command only), we can't auto-create here.
        return chart

    fields = {f.name: f for f in AccountModel._meta.fields}

    def upsert(code: str, name: str):
        qs = AccountModel.objects.filter(code=str(code)).filter(
            **{chart_fk_field: chart}
        )
        obj = qs.first()
        if obj:
            if "is_active" in fields and getattr(obj, "is_active", True) is not True:
                setattr(obj, "is_active", True)
                obj.save(update_fields=["is_active"])
            return obj

        payload = {chart_fk_field: chart, "code": str(code)}
        if "name" in fields:
            payload["name"] = name
        if "is_active" in fields:
            payload["is_active"] = True

        for fname, field in fields.items():
            if fname in payload:
                continue
            if getattr(field, "primary_key", False) or getattr(
                field, "auto_created", False
            ):
                continue
            if hasattr(field, "has_default") and field.has_default():
                continue
            if getattr(field, "null", False):
                continue
            if field.is_relation and getattr(field, "many_to_one", False):
                continue

            val = _default_for_field(field)
            if val is not None:
                payload[fname] = val

        for _ in range(6):
            try:
                return AccountModel.objects.create(**payload)
            except ValidationError as exc:
                msg = getattr(exc, "message_dict", {}) or {}
                if not msg:
                    raise
                for fn in msg.keys():
                    if fn in payload:
                        continue
                    if fn == "code":
                        payload["code"] = str(code)
                        continue
                    if fn == "name" and "name" in fields:
                        payload["name"] = name
                        continue
                    field = fields.get(fn)
                    if field is None:
                        raise
                    val = _default_for_field(field)
                    if val is not None:
                        payload[fn] = val
                    else:
                        raise

        raise ValidationError(
            f"Unable to create required account code={code} for refund tests."
        )

    # Seed common posting codes (based on earlier failures in POS)
    upsert("4000", "Sales Revenue")
    upsert("2100", "Tax / VAT Payable")
    upsert("1000", "Cash")
    upsert("1200", "Inventory")
    upsert("5000", "Cost of Goods Sold")

    return chart


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

        # Ensure accounting prerequisites exist for refund posting/reversal
        _create_active_chart_and_accounts()

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
            unit_price=Decimal("100.00"),
            is_active=True,
        )

        today = timezone.now().date()

        self.batch = StockBatch.objects.create(
            product=self.product,
            batch_number="BATCH-001",
            expiry_date=today + timedelta(days=365),
            quantity_received=10,
            quantity_remaining=10,
            unit_cost=Decimal("50.00"),
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
            subtotal_amount=Decimal("200.00"),
            total_amount=Decimal("200.00"),
            completed_at=timezone.now(),
        )

        self.item = SaleItem.objects.create(
            sale=self.sale,
            product=self.product,
            batch_reference=self.batch,
            quantity=2,
            unit_price=Decimal("100.00"),
            total_price=Decimal("200.00"),
        )

        # Critical: create SALE stock movements (refund restores from movement history)
        deduct_stock_fifo(
            product=self.product,
            quantity=self.item.quantity,
            user=self.pharmacist,
            sale=self.sale,
            store=None,
        )

        self.refund_url = reverse("sales-detail", args=[self.sale.id]) + "refund/"

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

        if response.status_code != status.HTTP_200_OK:
            print("\n[DEBUG] refund failed")
            print("HTTP:", response.status_code)
            try:
                print("DATA:", response.data)
            except Exception:
                print("RAW:", getattr(response, "content", b"")[:2000])

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.sale.refresh_from_db()
        self.batch.refresh_from_db()

        # Sale state updated
        self.assertEqual(self.sale.status, Sale.STATUS_REFUNDED)

        # Audit created exactly once
        self.assertEqual(RefundAudit.objects.filter(sale=self.sale).count(), 1)

        # Stock restored: started 10, sold 2 -> 8, refunded -> back to 10
        self.assertEqual(int(self.batch.quantity_remaining), 10)

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
        self.assertEqual(int(self.batch.quantity_remaining), 8)
        self.assertEqual(RefundAudit.objects.filter(sale=self.sale).count(), 0)

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
        self.assertEqual(int(self.batch.quantity_remaining), 8)
        self.assertEqual(RefundAudit.objects.filter(sale=self.sale).count(), 1)

    # ======================================================
    # INVALID STATE BLOCKED
    # ======================================================

    def test_refund_fails_if_sale_not_completed(self):
        self.client.force_authenticate(self.pharmacist)

        # Create a sale that is NOT completed (avoid mutating completed sale -> immutability rule)
        bad_sale = Sale.objects.create(
            invoice_no="INV-001-BAD",
            user=self.pharmacist,
            payment_method="cash",
            status=Sale.STATUS_REFUNDED,  # any non-completed state should be rejected
            subtotal_amount=Decimal("200.00"),
            total_amount=Decimal("200.00"),
            completed_at=timezone.now(),
        )
        bad_url = reverse("sales-detail", args=[bad_sale.id]) + "refund/"

        response = self.client.post(bad_url, {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
