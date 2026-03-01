# ============================================================
# PATH: sales/models/sale.py
# ============================================================

import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Sum
from django.utils import timezone

User = settings.AUTH_USER_MODEL


class Sale(models.Model):
    STATUS_DRAFT = "draft"
    STATUS_COMPLETED = "completed"
    STATUS_REFUNDED = "refunded"

    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_REFUNDED, "Refunded"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    invoice_no = models.CharField(max_length=64, unique=True, blank=True)

    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="sales",
    )

    subtotal_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))

    cogs_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    gross_profit_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))

    payment_method = models.CharField(max_length=32, default="cash")

    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default=STATUS_COMPLETED)

    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    # ============================================================
    # REFUND AGGREGATES (CRITICAL FIX)
    # ============================================================

    @property
    def total_refunded_amount(self):
        return (
            self.refund_audits.aggregate(total=Sum("total_amount"))["total"]
            or Decimal("0.00")
        )

    @property
    def remaining_refundable_amount(self):
        return Decimal(self.total_amount) - Decimal(self.total_refunded_amount)

    # ============================================================

    def save(self, *args, **kwargs):
        if not self.invoice_no:
            prefix = timezone.now().strftime("INV%Y%m%d")
            self.invoice_no = f"{prefix}-{uuid.uuid4().hex[:8].upper()}"

        if self.status == self.STATUS_COMPLETED and not self.completed_at:
            self.completed_at = timezone.now()

        try:
            self.gross_profit_amount = Decimal(self.subtotal_amount) - Decimal(self.cogs_amount)
        except Exception:
            pass

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.invoice_no} | {self.total_amount}"