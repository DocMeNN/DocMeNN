# sales/models/sale.py

import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone

User = settings.AUTH_USER_MODEL


class Sale(models.Model):
    """
    Represents a completed POS transaction.

    GUARANTEES:
    - Immutable financial record (after completion)
    - Stock is mutated ONLY via FIFO service
    - Safe for accounting, reporting, and audits

    HOTSPRINT UPGRADE:
    - cogs_amount: cost of goods sold (derived from FIFO movements at checkout)
    - gross_profit_amount: subtotal_amount - cogs_amount

    SPLIT PAYMENT:
    - payment_method may be "split"
    - split legs live in SalePaymentAllocation (related_name="payment_allocations")
    """

    STATUS_DRAFT = "draft"
    STATUS_COMPLETED = "completed"
    STATUS_REFUNDED = "refunded"

    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_REFUNDED, "Refunded"),
    ]

    STATUS_ENUM = {
        STATUS_DRAFT: {"label": "Draft", "terminal": False, "refundable": False},
        STATUS_COMPLETED: {"label": "Completed", "terminal": False, "refundable": True},
        STATUS_REFUNDED: {"label": "Refunded", "terminal": True, "refundable": False},
    }

    @classmethod
    def get_status_enum(cls):
        return cls.STATUS_ENUM

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    invoice_no = models.CharField(
        max_length=64,
        unique=True,
        blank=True,
        help_text="System-generated invoice / receipt number",
    )

    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="sales",
        help_text="Cashier / staff who processed the sale",
    )

    subtotal_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    tax_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    discount_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    total_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )

    cogs_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Total Cost of Goods Sold for this sale (FIFO-derived).",
    )

    gross_profit_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Gross profit = subtotal_amount - cogs_amount.",
    )

    payment_method = models.CharField(
        max_length=32,
        default="cash",
        help_text="cash/bank/pos/transfer/credit/split",
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

    _IMMUTABLE_FIELDS_AFTER_POST = (
        "user",
        "subtotal_amount",
        "tax_amount",
        "discount_amount",
        "total_amount",
        "cogs_amount",
        "gross_profit_amount",
        "payment_method",
        "created_at",
        "completed_at",
    )

    def _is_financially_locked(self, previous: "Sale") -> bool:
        return previous.status in (self.STATUS_COMPLETED, self.STATUS_REFUNDED)

    def _validate_immutable(self, previous: "Sale"):
        if not self._is_financially_locked(previous):
            return

        if (
            previous.status == self.STATUS_COMPLETED
            and self.status == self.STATUS_REFUNDED
        ):
            pass
        else:
            if self.status != previous.status:
                raise ValueError(
                    f"Sale is immutable once {previous.status}. "
                    f"Status change {previous.status} -> {self.status} is not allowed."
                )

        for field in self._IMMUTABLE_FIELDS_AFTER_POST:
            if getattr(self, field) != getattr(previous, field):
                raise ValueError(
                    f"Sale is immutable once {previous.status}. "
                    f"Field '{field}' cannot be changed."
                )

    def save(self, *args, **kwargs):
        if self.pk and not self._state.adding:
            previous = Sale.objects.filter(pk=self.pk).first()
            if previous is not None:
                self._validate_immutable(previous)

        if not self.invoice_no:
            prefix = timezone.now().strftime("INV%Y%m%d")
            self.invoice_no = f"{prefix}-{uuid.uuid4().hex[:8].upper()}"

        if self.status == self.STATUS_COMPLETED and not self.completed_at:
            self.completed_at = timezone.now()

        try:
            self.gross_profit_amount = Decimal(self.subtotal_amount) - Decimal(
                self.cogs_amount
            )
        except Exception:
            pass

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.invoice_no} | {self.total_amount}"
