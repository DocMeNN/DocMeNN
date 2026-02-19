# sales/models/refund_audit.py

"""
SALE REFUND AUDIT (IMMUTABLE)

Compatibility layer:
- Tests/legacy code expect class name: RefundAudit
- Your current class is: SaleRefundAudit
"""

import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone

from .sale import Sale

User = settings.AUTH_USER_MODEL


class SaleRefundAudit(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    sale = models.OneToOneField(
        Sale,
        on_delete=models.PROTECT,
        related_name="refund_audit",
    )

    refunded_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="processed_refunds",
    )

    reason = models.TextField(null=True, blank=True, help_text="Optional refund reason")
    refunded_at = models.DateTimeField(default=timezone.now)

    original_subtotal_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    original_tax_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    original_discount_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    original_total_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )

    original_cogs_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    original_gross_profit_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )

    class Meta:
        ordering = ["-refunded_at"]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise RuntimeError("SaleRefundAudit records are immutable")

        self.original_subtotal_amount = Decimal(
            getattr(self.sale, "subtotal_amount", 0) or 0
        )
        self.original_tax_amount = Decimal(getattr(self.sale, "tax_amount", 0) or 0)
        self.original_discount_amount = Decimal(
            getattr(self.sale, "discount_amount", 0) or 0
        )
        self.original_total_amount = Decimal(getattr(self.sale, "total_amount", 0) or 0)

        self.original_cogs_amount = Decimal(getattr(self.sale, "cogs_amount", 0) or 0)
        self.original_gross_profit_amount = Decimal(
            getattr(self.sale, "gross_profit_amount", 0) or 0
        )

        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise RuntimeError("SaleRefundAudit records cannot be deleted")

    def __str__(self):
        inv = getattr(self.sale, "invoice_no", None) or str(self.sale_id)
        return f"Refund | {inv}"


# ---------------------------------------------------------
# Legacy alias (tests expect RefundAudit)
# ---------------------------------------------------------
RefundAudit = SaleRefundAudit
