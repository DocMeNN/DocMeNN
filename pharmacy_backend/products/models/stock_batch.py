# products/models/stock_batch.py

"""
STOCK BATCH (DELIVERY-BASED INVENTORY)

Represents ONE physical delivery of stock.

CANONICAL MODEL (PHASE 2):
- StockBatch = one delivery
- store-scoped inventory (multi-store ready)
- quantity_received is immutable after creation
- quantity_remaining is mutated ONLY via services
- is_active is ALWAYS derived (never user-controlled)
- Non-deletable once referenced by StockMovement (audit safety)

HOTSPRINT UPGRADE (PURCHASE-COST READY):
- unit_cost is the cost basis for valuation + COGS.
- Migration-safe approach:
  - unit_cost is nullable to allow existing legacy batches to remain truthful (unknown cost).
  - NEW stock intake must supply unit_cost.
  - SALE/REFUND from unknown-cost batches must be blocked at service layer.
"""

import uuid
from decimal import Decimal

from django.db import models
from django.db.models import Q, F
from django.core.exceptions import ValidationError

from .product import Product
from store.models import Store


class StockBatch(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Store scope (PHASE 2.1)
    # NOTE: kept nullable for smooth migration; will be enforced later.
    store = models.ForeignKey(
        Store,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="stock_batches",
    )

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="stock_batches",
    )

    batch_number = models.CharField(
        max_length=128,
        help_text="Supplier / delivery batch reference",
    )

    expiry_date = models.DateField()

    quantity_received = models.PositiveIntegerField(
        help_text="Quantity delivered (immutable)"
    )

    quantity_remaining = models.PositiveIntegerField(
        default=0,
        help_text="Remaining quantity (service-managed only)",
    )

    # ✅ Cost basis (immutable once set)
    #
    # IMPORTANT (migration safety):
    # Existing batches may not have a known cost yet. We MUST NOT invent defaults.
    # Therefore unit_cost is nullable, and correctness is enforced in services.
    unit_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        default=None,
        help_text="Unit purchase cost for this batch (immutable once set; may be null for legacy batches).",
    )

    # Derived field — NEVER edited directly
    is_active = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["expiry_date", "created_at"]
        indexes = [
            models.Index(fields=["store", "created_at"]),
            models.Index(fields=["store", "expiry_date"]),
            models.Index(fields=["product", "expiry_date"]),
            models.Index(fields=["product", "is_active", "expiry_date"]),
            models.Index(fields=["expiry_date"]),
            models.Index(fields=["created_at"]),
        ]
        constraints = [
            # Multi-store safe uniqueness:
            # same batch_number can exist for same product in different stores.
            models.UniqueConstraint(
                fields=["store", "product", "batch_number"],
                name="unique_batch_per_store_product",
            ),
            models.CheckConstraint(
                condition=Q(quantity_received__gt=0),
                name="chk_stockbatch_qty_received_gt_zero",
            ),
            models.CheckConstraint(
                condition=Q(quantity_remaining__gte=0),
                name="chk_stockbatch_qty_remaining_gte_zero",
            ),
            models.CheckConstraint(
                condition=Q(quantity_remaining__lte=F("quantity_received")),
                name="chk_stockbatch_remaining_lte_received",
            ),
            # NOTE:
            # We intentionally DO NOT add a DB check constraint for unit_cost > 0
            # because legacy rows may have unit_cost=NULL during migration.
            # Enforcement is done in services for new intakes and for sale/refund.
        ]

    # -------------------------------------------------
    # VALIDATION
    # -------------------------------------------------

    def clean(self):
        if self.quantity_received <= 0:
            raise ValidationError(
                {"quantity_received": "quantity_received must be greater than zero"}
            )

        if self.quantity_remaining < 0:
            raise ValidationError(
                {"quantity_remaining": "quantity_remaining cannot be negative"}
            )

        if self.quantity_remaining > self.quantity_received:
            raise ValidationError(
                {"quantity_remaining": "quantity_remaining cannot exceed quantity_received"}
            )

        if not self.expiry_date:
            raise ValidationError({"expiry_date": "expiry_date is required"})

        # unit_cost validation:
        # - We allow NULL for legacy batches (truthful unknown cost).
        # - If provided, it must be > 0.
        if self.unit_cost is not None and self.unit_cost <= Decimal("0.00"):
            raise ValidationError({"unit_cost": "unit_cost must be greater than zero"})

        # Derive store from product if not explicitly set
        if not self.store_id:
            product_store_id = getattr(self.product, "store_id", None)
            if product_store_id:
                self.store_id = product_store_id

        # If both present, they must match
        if self.store_id and getattr(self.product, "store_id", None):
            if self.store_id != self.product.store_id:
                raise ValidationError({"store": "StockBatch.store must match Product.store"})

    # -------------------------------------------------
    # IMMUTABILITY + DERIVED STATE
    # -------------------------------------------------

    def save(self, *args, **kwargs):
        if not self._state.adding:
            original = StockBatch.objects.only("quantity_received", "unit_cost").get(pk=self.pk)

            if self.quantity_received != original.quantity_received:
                raise ValidationError({"quantity_received": "quantity_received is immutable"})

            # unit_cost is immutable once set.
            # Allow: None -> positive value (backfill correction)
            # Block: any change once original has a value (including value -> None or value -> other value)
            if original.unit_cost is not None:
                if self.unit_cost != original.unit_cost:
                    raise ValidationError({"unit_cost": "unit_cost is immutable once set"})
            else:
                # original was None; allow setting it (but not to invalid values)
                if self.unit_cost is not None and self.unit_cost <= Decimal("0.00"):
                    raise ValidationError({"unit_cost": "unit_cost must be greater than zero"})

        # is_active is ALWAYS derived
        self.is_active = int(self.quantity_remaining or 0) > 0

        self.full_clean()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        """
        Audit safety: once a batch has movements, it must never be deleted.
        """
        from products.models.stock_movement import StockMovement

        if StockMovement.objects.filter(batch=self).exists():
            raise ValidationError("Cannot delete StockBatch: it has StockMovement audit history.")
        return super().delete(*args, **kwargs)

    # -------------------------------------------------
    # READ-ONLY HELPERS
    # -------------------------------------------------

    @property
    def is_received(self) -> bool:
        return int(self.quantity_remaining or 0) > 0 or bool(self.is_active)

    @property
    def total_received_cost(self) -> Decimal:
        """
        Total cost of the delivered quantity (audit reconstruction).
        If cost is unknown, returns 0 (caller can treat as unknown).
        """
        unit_cost = self.unit_cost if self.unit_cost is not None else Decimal("0.00")
        return unit_cost * Decimal(int(self.quantity_received or 0))

    @property
    def total_remaining_value(self) -> Decimal:
        """
        Inventory valuation for remaining quantity in this batch.
        If cost is unknown, returns 0 (caller can treat as unknown).
        """
        unit_cost = self.unit_cost if self.unit_cost is not None else Decimal("0.00")
        return unit_cost * Decimal(int(self.quantity_remaining or 0))

    def __str__(self):
        product_name = getattr(self.product, "name", "Product")
        store_name = getattr(getattr(self, "store", None), "name", "NO-STORE")
        return f"{store_name} | {product_name} | Batch {self.batch_number}"
