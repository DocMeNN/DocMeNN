# purchases/models.py

import uuid
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from products.models.product import Product
from store.models.store import Store

TWOPLACES = Decimal("0.01")


def _money(v) -> Decimal:
    return Decimal(str(v or "0.00")).quantize(TWOPLACES)


User = settings.AUTH_USER_MODEL


class Supplier(models.Model):
    """
    Supplier master.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    name = models.CharField(max_length=200)
    phone = models.CharField(max_length=50, blank=True, default="")
    email = models.EmailField(blank=True, default="")
    address = models.TextField(blank=True, default="")

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        indexes = [
            models.Index(fields=["name"]),
            models.Index(fields=["is_active"]),
        ]

    def __str__(self):
        return self.name


class PurchaseInvoice(models.Model):
    """
    Supplier invoice header.

    Receiving is performed by services:
    - posts to ledger FIRST (idempotent)
    - intakes stock (StockBatch + StockMovement(RECEIPT))
    - marks invoice RECEIVED
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    STATUS_DRAFT = "DRAFT"
    STATUS_RECEIVED = "RECEIVED"
    STATUS_CANCELLED = "CANCELLED"

    STATUSES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_RECEIVED, "Received"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    # Phase 2: multi-store ready (optional for backward compat)
    store = models.ForeignKey(
        Store,
        on_delete=models.PROTECT,
        related_name="purchase_invoices",
        null=True,
        blank=True,
    )

    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.PROTECT,
        related_name="invoices",
    )

    invoice_number = models.CharField(max_length=64)
    invoice_date = models.DateField(default=timezone.localdate)

    status = models.CharField(max_length=20, choices=STATUSES, default=STATUS_DRAFT)

    subtotal_amount = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal("0.00")
    )
    total_amount = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal("0.00")
    )

    received_at = models.DateTimeField(null=True, blank=True)

    # Audit (optional, but very useful)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="purchase_invoices_created",
    )
    received_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="purchase_invoices_received",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["supplier", "invoice_number"],
                name="uniq_supplier_invoice_number",
            ),
            # NOTE: older Django expects `condition=` not `check=`
            models.CheckConstraint(
                condition=models.Q(subtotal_amount__gte=Decimal("0.00")),
                name="purchase_invoice_subtotal_nonnegative",
            ),
            models.CheckConstraint(
                condition=models.Q(total_amount__gte=Decimal("0.00")),
                name="purchase_invoice_total_nonnegative",
            ),
        ]
        indexes = [
            models.Index(fields=["supplier", "invoice_number"]),
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["store", "created_at"]),
        ]

    def clean(self):
        if not (self.invoice_number or "").strip():
            raise ValidationError({"invoice_number": "invoice_number is required"})

        if self.subtotal_amount is not None and self.subtotal_amount < Decimal("0.00"):
            raise ValidationError(
                {"subtotal_amount": "subtotal_amount cannot be negative"}
            )

        if self.total_amount is not None and self.total_amount < Decimal("0.00"):
            raise ValidationError({"total_amount": "total_amount cannot be negative"})

        if self.status == self.STATUS_RECEIVED and not self.received_at:
            raise ValidationError(
                {"received_at": "received_at is required when status is RECEIVED"}
            )

        if self.status == self.STATUS_CANCELLED and self.received_at:
            raise ValidationError(
                {"received_at": "received_at must be empty when status is CANCELLED"}
            )

    def save(self, *args, **kwargs):
        if self.invoice_number is not None:
            self.invoice_number = self.invoice_number.strip()

        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.invoice_number} ({self.supplier.name})"


class PurchaseInvoiceItem(models.Model):
    """
    Supplier invoice line.

    batch_number is REQUIRED to generate StockBatch safely (unique per product).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    invoice = models.ForeignKey(
        PurchaseInvoice,
        on_delete=models.CASCADE,
        related_name="items",
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name="purchase_invoice_items",
    )

    batch_number = models.CharField(
        max_length=128,
        help_text="Supplier / delivery batch reference",
    )
    expiry_date = models.DateField()

    quantity = models.PositiveIntegerField()
    unit_cost = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal("0.00")
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0),
                name="purchase_invoice_item_quantity_gt_zero",
            ),
            models.CheckConstraint(
                condition=models.Q(unit_cost__gte=Decimal("0.00")),
                name="purchase_invoice_item_unit_cost_nonnegative",
            ),
            models.UniqueConstraint(
                fields=["invoice", "product", "batch_number"],
                name="uniq_invoice_product_batchnumber",
            ),
        ]
        indexes = [
            models.Index(fields=["invoice", "created_at"]),
            models.Index(fields=["product", "created_at"]),
        ]

    def clean(self):
        if not (self.batch_number or "").strip():
            raise ValidationError({"batch_number": "batch_number is required"})

        if self.unit_cost is not None and self.unit_cost < Decimal("0.00"):
            raise ValidationError({"unit_cost": "unit_cost cannot be negative"})

        if self.expiry_date is None:
            raise ValidationError({"expiry_date": "expiry_date is required"})

    @property
    def line_total(self) -> Decimal:
        return _money(Decimal(str(self.quantity)) * Decimal(str(self.unit_cost)))

    def save(self, *args, **kwargs):
        if self.batch_number is not None:
            self.batch_number = self.batch_number.strip()
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        product_name = getattr(self.product, "name", "Product")
        return f"{product_name} x {self.quantity} ({self.batch_number})"


class SupplierPayment(models.Model):
    """
    Supplier payment to settle Accounts Payable.

    Design:
    - Optional link to invoice (can pay a specific invoice)
    - Ledger posting is idempotent via payment_id
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.PROTECT,
        related_name="payments",
    )
    invoice = models.ForeignKey(
        PurchaseInvoice,
        on_delete=models.PROTECT,
        related_name="payments",
        null=True,
        blank=True,
        help_text="Optional: payment for a specific invoice",
    )

    payment_date = models.DateField(default=timezone.localdate)
    amount = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal("0.00")
    )

    METHOD_CASH = "cash"
    METHOD_BANK = "bank"

    METHODS = [
        (METHOD_CASH, "Cash"),
        (METHOD_BANK, "Bank"),
    ]

    payment_method = models.CharField(
        max_length=20, choices=METHODS, default=METHOD_CASH
    )
    narration = models.CharField(max_length=255, blank=True, default="")

    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="supplier_payments_created",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gt=Decimal("0.00")),
                name="supplier_payment_amount_gt_zero",
            ),
        ]
        indexes = [
            models.Index(fields=["supplier", "created_at"]),
            models.Index(fields=["invoice", "created_at"]),
        ]

    def clean(self):
        if self.payment_method not in {self.METHOD_CASH, self.METHOD_BANK}:
            raise ValidationError({"payment_method": "Invalid payment_method"})

        if self.amount is not None and self.amount <= Decimal("0.00"):
            raise ValidationError({"amount": "amount must be > 0"})

    def save(self, *args, **kwargs):
        if self.narration is not None:
            self.narration = self.narration.strip()
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        inv = f" ({self.invoice.invoice_number})" if self.invoice else ""
        return f"{self.supplier.name}{inv} - {self.amount}"
