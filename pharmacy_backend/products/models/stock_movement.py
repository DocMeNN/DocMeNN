# products/models/stock_movement.py

"""
CANONICAL INVENTORY LEDGER (PHASE 2)

Immutable inventory ledger entry.

GUARANTEES:
- Append-only (no updates, no deletes)
- Created ONCE, never edited
- Movement direction validated against reason
- Sale-linked movements must reference a sale

HOTSPRINT UPGRADE (COST-SNAPSHOT READY):
- unit_cost_snapshot is stored per movement for audit reconstruction.
- New writes MUST populate it whenever batch has a unit_cost.
- Legacy rows may exist with NULL snapshot (handled by backfill command).
"""

import uuid
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from .product import Product
from .stock_batch import StockBatch


class StockMovement(models.Model):
    class MovementType(models.TextChoices):
        IN = "IN", "Stock In"
        OUT = "OUT", "Stock Out"

    class Reason(models.TextChoices):
        RECEIPT = "RECEIPT", "Stock Receipt"
        SALE = "SALE", "Sale"
        REFUND = "REFUND", "Sale Refund"
        ADJUSTMENT = "ADJUSTMENT", "Manual Adjustment"
        EXPIRY = "EXPIRY", "Expired Stock"

    REASON_TO_MOVEMENT = {
        Reason.RECEIPT: MovementType.IN,
        Reason.REFUND: MovementType.IN,
        Reason.SALE: MovementType.OUT,
        Reason.EXPIRY: MovementType.OUT,
        Reason.ADJUSTMENT: None,
    }

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="stock_movements"
    )
    batch = models.ForeignKey(
        StockBatch, on_delete=models.CASCADE, related_name="stock_movements"
    )

    movement_type = models.CharField(max_length=3, choices=MovementType.choices)
    reason = models.CharField(max_length=20, choices=Reason.choices)

    quantity = models.PositiveIntegerField()

    # Migration-safe nullable; new flows should populate it.
    unit_cost_snapshot = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        default=None,
        help_text="Unit cost snapshot from batch at movement time (immutable).",
    )

    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stock_movements",
    )

    sale = models.ForeignKey(
        "sales.Sale",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stock_movements",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["created_at"]),
            models.Index(fields=["reason"]),
            models.Index(fields=["movement_type"]),
            models.Index(fields=["product", "created_at"]),
            models.Index(fields=["batch", "created_at"]),
            models.Index(fields=["sale", "created_at"]),
        ]

    def clean(self):
        if self.quantity <= 0:
            raise ValidationError("quantity must be greater than zero")

        # Validate batch-product consistency
        if self.batch_id and self.product_id:
            batch_vals = (
                StockBatch.objects.filter(id=self.batch_id)
                .values("product_id", "unit_cost")
                .first()
            )
            if batch_vals and batch_vals["product_id"] != self.product_id:
                raise ValidationError("Batch does not belong to product")

        expected_type = self.REASON_TO_MOVEMENT.get(self.reason)
        if expected_type and self.movement_type != expected_type:
            raise ValidationError(
                f"{self.reason} requires movement_type={expected_type}"
            )

        if self.reason in {self.Reason.SALE, self.Reason.REFUND} and not self.sale_id:
            raise ValidationError("SALE / REFUND must reference a sale")

        # If batch has a unit_cost, require snapshot for ALL reasons for new writes.
        if self.batch_id:
            batch_cost = (
                StockBatch.objects.filter(id=self.batch_id)
                .values_list("unit_cost", flat=True)
                .first()
            )
            if batch_cost is not None and self.unit_cost_snapshot is None:
                raise ValidationError(
                    "unit_cost_snapshot is required when batch.unit_cost is set"
                )

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("StockMovement records are immutable")

        # Derive cost snapshot from batch if not explicitly set
        if self.unit_cost_snapshot is None and self.batch_id:
            self.unit_cost_snapshot = (
                StockBatch.objects.filter(id=self.batch_id)
                .values_list("unit_cost", flat=True)
                .first()
            )

        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError(
            "StockMovement records are immutable and cannot be deleted"
        )

    @property
    def total_cost(self) -> Decimal:
        unit_cost = (
            self.unit_cost_snapshot
            if self.unit_cost_snapshot is not None
            else Decimal("0.00")
        )
        return unit_cost * Decimal(int(self.quantity or 0))

    def __str__(self):
        product_name = getattr(self.product, "name", "Product")
        return f"{product_name} | {self.reason} | {self.quantity}"
