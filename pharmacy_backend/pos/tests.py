# pos/tests.py

"""
POS TESTS

Run with:
    python manage.py test pos -v 2

Checkout touches:
POS -> Sales -> FIFO -> Accounting

Therefore tests MUST seed:
- active cart
- stock batch WITH unit_cost
- active Chart of Accounts (with required custom validation fields like `code`)
- required Chart Accounts (e.g. 4000, 2100) used by posting services
"""

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

from pos.models import Cart, CartItem
from products.models import Product, StockBatch
from sales.models import Sale, SaleItem

User = get_user_model()


# -----------------------------
# User creation (CI-safe)
# -----------------------------


def _create_test_user(*, email: str, username: str, password: str):
    """
    CI requires create_user(email=...) in your custom UserManager.
    Locally you may have allowed username-only, but CI is the source of truth.
    """
    kwargs = {"email": email, "password": password}

    # Only pass username if the model actually has it
    user_field_names = {f.name for f in User._meta.fields}
    if "username" in user_field_names:
        kwargs["username"] = username

    return User.objects.create_user(**kwargs)


# -----------------------------
# Generic helpers (test seeding)
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


def _create_chart_with_retries(ChartOfAccounts):
    """
    ChartOfAccounts.save() calls full_clean(); it requires code.
    We'll satisfy: code + name + is_active, and fill other required fields.
    """
    active = ChartOfAccounts.objects.filter(is_active=True).first()
    if active:
        return active

    fields = {f.name: f for f in ChartOfAccounts._meta.fields}
    payload = {"is_active": True}

    if "code" in fields:
        payload["code"] = f"TEST-COA-{uuid.uuid4().hex[:6].upper()}"
    if "name" in fields:
        payload["name"] = "Test Chart of Accounts"

    # Pre-fill obvious required fields (non-null, no-default)
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

    # Retry on ValidationError to satisfy extra custom requirements
    for _ in range(6):
        try:
            obj = ChartOfAccounts.objects.create(**payload)
            ChartOfAccounts.objects.exclude(id=obj.id).update(is_active=False)
            return obj
        except ValidationError as exc:
            msg = getattr(exc, "message_dict", {}) or {}
            if not msg:
                raise
            for field_name in msg.keys():
                if field_name in payload:
                    continue
                if field_name == "code":
                    payload["code"] = f"TEST-COA-{uuid.uuid4().hex[:6].upper()}"
                    continue
                if field_name == "name":
                    payload["name"] = "Test Chart of Accounts"
                    continue

                field = fields.get(field_name)
                if field is None:
                    raise
                val = _default_for_field(field)
                if val is not None:
                    payload[field_name] = val
                else:
                    raise

    raise ValidationError("Unable to create a valid active ChartOfAccounts for tests.")


def _find_chart_account_model(ChartOfAccounts):
    """
    Find the model that represents accounts inside a chart.
    Heuristic:
    - has field 'code'
    - has a FK to ChartOfAccounts
    """
    candidates = []
    for m in apps.get_models():
        field_names = {f.name for f in m._meta.fields}
        if "code" not in field_names:
            continue

        for f in m._meta.fields:
            if (
                f.is_relation
                and getattr(f, "many_to_one", False)
                and getattr(f.remote_field, "model", None) == ChartOfAccounts
            ):
                candidates.append((m, f.name))
                break

    preferred_names = {"Account", "ChartAccount", "ChartAccountItem", "AccountCode"}
    for m, fk_name in candidates:
        if m.__name__ in preferred_names:
            return m, fk_name

    return candidates[0] if candidates else (None, None)


def _ensure_chart_accounts(chart):
    """
    Ensure posting-required accounts exist in the active chart.
    """
    ChartOfAccounts = chart.__class__
    AccountModel, chart_fk_field = _find_chart_account_model(ChartOfAccounts)
    if AccountModel is None:
        raise RuntimeError(
            "Could not locate Chart Account model (needs field 'code' and FK to ChartOfAccounts). "
            "Paste your accounting account model so we wire this correctly."
        )

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
            f"Unable to create required account code={code} for tests."
        )

    # Required by failures so far:
    upsert("4000", "Sales Revenue")
    upsert("2100", "Tax / VAT Payable")

    # Proactively seed likely next required codes:
    upsert("1000", "Cash")
    upsert("1200", "Inventory")
    upsert("5000", "Cost of Goods Sold")

    # Optional common liabilities (harmless if unused):
    upsert("2000", "Accounts Payable")
    upsert("2300", "Accrued Expenses / Payables")


def _ensure_active_chart_of_accounts():
    from accounting.models.chart import ChartOfAccounts

    chart = _create_chart_with_retries(ChartOfAccounts)
    _ensure_chart_accounts(chart)
    return chart


# -----------------------------
# Tests
# -----------------------------


class POSBaseTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()

        self.cashier = _create_test_user(
            email="cashier@example.com",
            username="cashier",
            password="testpass123",
        )
        self.client.force_authenticate(user=self.cashier)

        # ✅ Seed active chart + required accounts (4000, 2100, etc.)
        _ensure_active_chart_of_accounts()

        self.product = Product.objects.create(
            sku="PARA-001",
            name="Paracetamol",
            unit_price=Decimal("100.00"),
            is_active=True,
        )

        self.batch = StockBatch.objects.create(
            product=self.product,
            batch_number="BATCH-001",
            expiry_date=date.today() + timedelta(days=365),
            quantity_received=50,
            quantity_remaining=50,
            unit_cost=Decimal("50.00"),
        )

        Cart.objects.get_or_create(
            user=self.cashier,
            store=None,
            is_active=True,
        )


class POSCartTests(POSBaseTestCase):
    def test_get_empty_cart(self):
        url = reverse("pos:active-cart")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["items"], [])
        self.assertEqual(Decimal(response.data["total_amount"]), Decimal("0.00"))

    def test_add_item_to_cart(self):
        url = reverse("pos:add-cart-item")
        response = self.client.post(
            url,
            {"product_id": str(self.product.id), "quantity": 2},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["items"]), 1)
        self.assertEqual(response.data["items"][0]["quantity"], 2)
        self.assertEqual(
            Decimal(response.data["items"][0]["unit_price"]), Decimal("100.00")
        )


class POSCheckoutTests(POSBaseTestCase):
    def test_checkout_success(self):
        cart = Cart.objects.get(user=self.cashier, is_active=True)

        CartItem.objects.create(
            cart=cart,
            product=self.product,
            quantity=3,
            unit_price=Decimal("100.00"),
        )

        url = reverse("pos:checkout")
        response = self.client.post(url, {"payment_method": "cash"}, format="json")

        if response.status_code != status.HTTP_201_CREATED:
            print("\n[DEBUG] POS checkout failed")
            print("HTTP:", response.status_code)
            try:
                print("DATA:", response.data)
            except Exception:
                print("RAW:", getattr(response, "content", b"")[:2000])

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        sale = Sale.objects.first()
        self.assertIsNotNone(sale)
        self.assertEqual(sale.total_amount, Decimal("300.00"))

        sale_item = SaleItem.objects.first()
        self.assertIsNotNone(sale_item)
        self.assertEqual(sale_item.quantity, 3)

        self.batch.refresh_from_db()
        self.assertEqual(int(self.batch.quantity_remaining), 47)

        self.assertEqual(cart.items.count(), 0)

    def test_checkout_empty_cart_fails(self):
        url = reverse("pos:checkout")
        response = self.client.post(url, {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
