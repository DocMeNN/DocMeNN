# ============================================================
# PATH: sales/models/refund_audit.py
# ============================================================

"""
SALE REFUND AUDIT (DELTA-BASED, MULTI-REFUND SAFE)

This model represents ONE refund event.

Each record stores the FINANCIAL DELTA for that specific refund.

Design:
- A sale can have multiple refund audits.
- Each refund audit represents an independent accounting event.
- Refund audits are immutable.
- Original sale money is NEVER mutated.

Best Practice:
- Never derive refund totals from Sale at posting time.
- Store authoritative refund delta values here.
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

    # 🔥 MULTI-REFUND SUPPORT
    sale = models.ForeignKey(
        Sale,
        on_delete=models.PROTECT,
        related_name="refund_audits",
    )

    refunded_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="processed_refunds",
    )

    reason = models.TextField(blank=True, null=True)
    refunded_at = models.DateTimeField(default=timezone.now)

    # ============================================================
    # REFUND DELTA AMOUNTS (THIS TRANSACTION ONLY)
    # ============================================================

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
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )

    gross_profit_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )

    # Accounting idempotency flag
    is_accounted = models.BooleanField(default=False)

    class Meta:
        ordering = ["-refunded_at"]
        indexes = [
            models.Index(fields=["sale"]),
            models.Index(fields=["refunded_at"]),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise RuntimeError("SaleRefundAudit records are immutable")

        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise RuntimeError("SaleRefundAudit records cannot be deleted")

    def __str__(self):
        return f"Refund {self.id} | {self.total_amount}"