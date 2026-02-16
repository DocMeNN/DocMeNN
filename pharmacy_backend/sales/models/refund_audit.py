# sales/models/refund_audit.py

"""
SALE REFUND AUDIT (IMMUTABLE)

Purpose:
- Immutable audit log for refunded sales (created once; never updated/deleted).
- Captures the *financial truth at refund time* so reporting + accounting can
  reconstruct exactly what happened.

HOTSPRINT UPGRADE (COGS + PROFIT READY):
- Snapshot original_subtotal_amount / tax / discount / total
- Snapshot original_cogs_amount and original_gross_profit_amount
  so refunds can reverse Inventory/COGS deterministically.
"""

import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone

from .sale import Sale

User = settings.AUTH_USER_MODEL


class SaleRefundAudit(models.Model):
    """
    Immutable audit log for refunded sales.
    Created once. Never updated. Never deleted.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

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

    reason = models.TextField(
        null=True,
        blank=True,
        help_text="Optional refund reason",
    )

    refunded_at = models.DateTimeField(default=timezone.now)

    # ----------------------------
    # Financial snapshots (original)
    # ----------------------------
    original_subtotal_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Subtotal at time of refund (snapshot).",
    )

    original_tax_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Tax at time of refund (snapshot).",
    )

    original_discount_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Discount at time of refund (snapshot).",
    )

    original_total_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Total at time of refund (snapshot).",
    )

    # ----------------------------
    # Cost & profit snapshots (original)
    # ----------------------------
    original_cogs_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="COGS at time of refund (snapshot for deterministic reversal).",
    )

    original_gross_profit_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Gross profit at time of refund (snapshot).",
    )

    class Meta:
        ordering = ["-refunded_at"]

    # ======================================================
    # IMMUTABILITY — CORRECT IMPLEMENTATION
    # ======================================================

    def save(self, *args, **kwargs):
        # Allow creation, block updates
        if not self._state.adding:
            raise RuntimeError("SaleRefundAudit records are immutable")

        # Snapshot financial truth ONCE (defensive defaults)
        self.original_subtotal_amount = Decimal(getattr(self.sale, "subtotal_amount", 0) or 0)
        self.original_tax_amount = Decimal(getattr(self.sale, "tax_amount", 0) or 0)
        self.original_discount_amount = Decimal(getattr(self.sale, "discount_amount", 0) or 0)
        self.original_total_amount = Decimal(getattr(self.sale, "total_amount", 0) or 0)

        # Snapshot cost/profit (if present on Sale model)
        self.original_cogs_amount = Decimal(getattr(self.sale, "cogs_amount", 0) or 0)
        self.original_gross_profit_amount = Decimal(getattr(self.sale, "gross_profit_amount", 0) or 0)

        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise RuntimeError("SaleRefundAudit records cannot be deleted")

    def __str__(self):
        inv = getattr(self.sale, "invoice_no", None) or str(self.sale_id)
        return f"Refund | {inv}"
