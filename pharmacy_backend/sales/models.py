# pharmacy_backend/sales/models.py

import uuid
from decimal import Decimal

from django.db import models
from django.conf import settings
from django.utils import timezone

from products.models import Product

User = settings.AUTH_USER_MODEL


# ======================================================================
# SALE (HEADER)
# ======================================================================

class Sale(models.Model):
    """
    Represents a completed POS transaction.
    Stock is mutated ONLY via FIFO service, not here.
    """

    STATUS_DRAFT = "draft"
    STATUS_COMPLETED = "completed"
    STATUS_REFUNDED = "refunded"

    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_REFUNDED, "Refunded"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    invoice_no = models.CharField(
        max_length=64,
        unique=True,
        blank=True,
    )

    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="sales",
        help_text="Cashier / staff who processed the sale",
    )

    subtotal_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Sum of line items before tax/discount",
    )

    tax_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    discount_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    total_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Final amount paid",
    )

    payment_method = models.CharField(
        max_length=32,
        default="cash",
    )

    status = models.CharField(
        max_length=32,
        choices=STATUS_CHOICES,
        default=STATUS_COMPLETED,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["created_at"]),
            models.Index(fields=["status"]),
            models.Index(fields=["invoice_no"]),
        ]

    def save(self, *args, **kwargs):
        # Generate invoice number on first save
        if not self.invoice_no:
            prefix = timezone.now().strftime("INV%Y%m%d")
            self.invoice_no = f"{prefix}-{uuid.uuid4().hex[:8].upper()}"

        # Auto-set completed timestamp
        if self.status == self.STATUS_COMPLETED and not self.completed_at:
            self.completed_at = timezone.now()

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.invoice_no} | {self.total_amount}"


# ======================================================================
# SALE ITEM (LINE ITEMS)
# ======================================================================

class SaleItem(models.Model):
    """
    Immutable snapshot of what was sold.
    Does NOT track stock directly.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    sale = models.ForeignKey(
        Sale,
        on_delete=models.CASCADE,
        related_name="items",
    )

    product = models.ForeignKey(
        Product,
        on_delete=models.SET_NULL,
        null=True,
        help_text="Product at time of sale",
    )

    batch_reference = models.CharField(
        max_length=128,
        blank=True,
        null=True,
        help_text="Optional batch number (for receipt / audit display)",
    )

    quantity = models.PositiveIntegerField()

    unit_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
    )

    total_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        editable=False,
    )

    class Meta:
        ordering = ["id"]
        indexes = [
            models.Index(fields=["sale"]),
            models.Index(fields=["product"]),
        ]

    def save(self, *args, **kwargs):
        # Always compute total from quantity * unit_price
        self.total_price = self.unit_price * self.quantity
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.product} x {self.quantity}"
