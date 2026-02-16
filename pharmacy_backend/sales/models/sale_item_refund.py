# sales/models/sale_item_refund.py

"""
======================================================
PATH: sales/models/sale_item_refund.py
======================================================
SALE ITEM REFUND (PARTIAL REFUND LEDGER)

Purpose:
- Immutable, append-only record of refunded quantities per SaleItem.
- Enables PARTIAL refunds with strict quantity enforcement.
- Serves as the single source of truth for:
    • remaining refundable quantity
    • stock restoration
    • accounting reversal

Design guarantees:
- Append-only (no updates, no deletes)
- Multiple refunds per sale_item allowed
- Over-refunding is prevented at service layer
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone

from .sale import Sale
from .sale_item import SaleItem

User = settings.AUTH_USER_MODEL


class SaleItemRefund(models.Model):
    """
    Immutable record of a refunded quantity for a specific SaleItem.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    sale = models.ForeignKey(
        Sale,
        on_delete=models.PROTECT,
        related_name="item_refunds",
    )

    sale_item = models.ForeignKey(
        SaleItem,
        on_delete=models.PROTECT,
        related_name="refunds",
    )

    quantity_refunded = models.PositiveIntegerField(
        help_text="Quantity refunded for this sale item (immutable)."
    )

    # Financial snapshots (authoritative at refund time)
    unit_price_snapshot = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text="Unit selling price at time of refund (snapshot).",
    )

    unit_cost_snapshot = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text="Unit cost at time of refund (snapshot).",
    )

    refunded_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="sale_item_refunds",
    )

    reason = models.TextField(
        null=True,
        blank=True,
        help_text="Optional refund reason.",
    )

    refunded_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["refunded_at"]
        indexes = [
            models.Index(fields=["sale", "refunded_at"]),
            models.Index(fields=["sale_item", "refunded_at"]),
        ]

    # --------------------------------------------------
    # IMMUTABILITY
    # --------------------------------------------------

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise RuntimeError("SaleItemRefund records are immutable")

        if self.quantity_refunded <= 0:
            raise ValueError("quantity_refunded must be greater than zero")

        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise RuntimeError("SaleItemRefund records cannot be deleted")

    # --------------------------------------------------
    # READ HELPERS
    # --------------------------------------------------

    @property
    def line_total_refund_amount(self) -> Decimal:
        return Decimal(self.unit_price_snapshot) * Decimal(self.quantity_refunded)

    @property
    def line_total_cost_refund_amount(self) -> Decimal:
        return Decimal(self.unit_cost_snapshot) * Decimal(self.quantity_refunded)

    def __str__(self):
        return f"Refund | {self.sale_item_id} | qty={self.quantity_refunded}"
