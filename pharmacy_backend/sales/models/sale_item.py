# sales/models/sale_item.py

"""
SALE ITEM (IMMUTABLE SNAPSHOT)

Represents an immutable snapshot of a sold line item.

Notes:
- SaleItem rows are append-only after SALE COMPLETION
- During checkout (sale.status=draft), we allow ONE controlled enrichment:
  writing FIFO-derived cost/profit snapshot fields, before the sale is completed.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from products.models import Product

from .sale import Sale


class SaleItem(models.Model):
    """
    Immutable snapshot of sold item.
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
    )

    # For traceability (optional): if one batch was used, store batch_number.
    # If multiple batches were used, store a short marker like "MULTI".
    batch_reference = models.CharField(
        max_length=128,
        blank=True,
        null=True,
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

    # ✅ HOTSPRINT: Cost/profit snapshots (FIFO-derived)
    unit_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="FIFO-derived unit cost at time of sale (snapshot).",
    )

    cost_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Total cost for this line (snapshot).",
    )

    gross_profit_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Line gross profit = total_price - cost_amount.",
    )

    # ✅ REQUIRED FOR CHRONOLOGICAL ORDERING + AUDITABILITY
    # Use default=timezone.now to avoid interactive migration prompts for existing rows.
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [
            models.Index(fields=["sale", "created_at"]),
            models.Index(fields=["product", "created_at"]),
        ]

    def _allow_draft_enrichment_only(self, previous: "SaleItem"):
        """
        Allow updating ONLY cost/profit snapshot fields while sale is still draft.
        This supports the checkout orchestrator which may compute FIFO cost after
        creating the sale item line.
        """
        if getattr(self.sale, "status", None) != Sale.STATUS_DRAFT:
            raise ValidationError(
                "SaleItem records are immutable once sale is not draft"
            )

        allowed = {
            "unit_cost",
            "cost_amount",
            "gross_profit_amount",
            "batch_reference",
            "total_price",
        }

        # Forbid any other edits
        for field in ("sale_id", "product_id", "quantity", "unit_price", "created_at"):
            if getattr(self, field) != getattr(previous, field):
                raise ValidationError(f"SaleItem field '{field}' is immutable")

        # Ensure only allowed fields changed
        changed = []
        for field in allowed:
            if getattr(self, field) != getattr(previous, field):
                changed.append(field)

        if not changed:
            raise ValidationError("No changes detected")

        return changed

    def save(self, *args, **kwargs):
        # Always keep total_price consistent
        self.total_price = Decimal(self.unit_price) * Decimal(int(self.quantity or 0))

        if not self._state.adding:
            previous = SaleItem.objects.filter(pk=self.pk).first()
            if previous is None:
                raise ValidationError("SaleItem records are immutable")

            # Controlled enrichment while sale is draft
            self._allow_draft_enrichment_only(previous)

        # Maintain profit consistency best-effort
        try:
            self.gross_profit_amount = Decimal(self.total_price) - Decimal(
                self.cost_amount
            )
        except Exception:
            pass

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.product} x {self.quantity}"
