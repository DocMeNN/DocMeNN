"""
PATH: products/models/stock_batch.py

STOCK BATCH (DELIVERY-BASED INVENTORY)

Compatibility goals (tests + legacy):
- Tests may create via ProductBatch (alias of StockBatch).
- Some tests/fixtures use legacy kwargs:
    - batch_no (instead of batch_number)
    - quantity (instead of quantity_received)
- Some legacy code provides quantity_remaining without quantity_received.
  In that case, derive quantity_received = quantity_remaining (safe default).
- On create: if quantity_remaining is not provided, default it to quantity_received.
"""

import uuid
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q

from .product import Product


class StockBatchManager(models.Manager):
    """
    Compatibility manager to absorb legacy kwargs used by tests/older code.
    """

    def create(self, **kwargs):
        # Legacy aliases
        if "batch_no" in kwargs and "batch_number" not in kwargs:
            kwargs["batch_number"] = kwargs.pop("batch_no")

        if "quantity" in kwargs and "quantity_received" not in kwargs:
            kwargs["quantity_received"] = kwargs.pop("quantity")

        # If caller sets remaining but forgot received, derive received.
        if "quantity_remaining" in kwargs and "quantity_received" not in kwargs:
            kwargs["quantity_received"] = kwargs["quantity_remaining"]

        # If caller sets received but didn't set remaining, default remaining to received.
        if "quantity_received" in kwargs and "quantity_remaining" not in kwargs:
            kwargs["quantity_remaining"] = kwargs["quantity_received"]

        return super().create(**kwargs)


class StockBatch(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    store = models.ForeignKey(
        "store.Store",
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
        blank=True,
        default="",
        help_text="Supplier / delivery batch reference (auto-generated if blank)",
    )

    expiry_date = models.DateField()

    quantity_received = models.PositiveIntegerField(
        default=1,
        help_text="Quantity delivered (immutable). Defaults to 1 for test compatibility.",
    )

    quantity_remaining = models.PositiveIntegerField(
        default=0,
        help_text="Remaining quantity (service-managed only). Defaults to quantity_received on create if not set.",
    )

    unit_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        default=None,
        help_text="Unit purchase cost for this batch (immutable once set; may be null for legacy batches).",
    )

    is_active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = StockBatchManager()

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
        ]

    def clean(self):
        if self.quantity_received is None or int(self.quantity_received) <= 0:
            raise ValidationError(
                {"quantity_received": "quantity_received must be greater than zero"}
            )

        # Allow save() to auto-fill remaining on create; but once set, validate.
        if self.quantity_remaining is None:
            raise ValidationError(
                {"quantity_remaining": "quantity_remaining is required"}
            )

        if int(self.quantity_remaining) < 0:
            raise ValidationError(
                {"quantity_remaining": "quantity_remaining cannot be negative"}
            )

        if int(self.quantity_remaining) > int(self.quantity_received):
            raise ValidationError(
                {
                    "quantity_remaining": "quantity_remaining cannot exceed quantity_received"
                }
            )

        if not self.expiry_date:
            raise ValidationError({"expiry_date": "expiry_date is required"})

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
                raise ValidationError(
                    {"store": "StockBatch.store must match Product.store"}
                )

    def save(self, *args, **kwargs):
        # Auto-generate a batch number if blank (test compatibility)
        if not (self.batch_number or "").strip():
            self.batch_number = f"AUTO-{uuid.uuid4().hex[:10].upper()}"

        # On create: if remaining wasn't explicitly set, default it to received.
        # Important: do NOT override an explicit remaining=0.
        if self._state.adding and self.quantity_remaining is None:
            self.quantity_remaining = int(self.quantity_received or 0)

        # If someone provided remaining but received is missing/incorrect (legacy),
        # normalize before validation.
        if self._state.adding:
            if self.quantity_received is None and self.quantity_remaining is not None:
                self.quantity_received = int(self.quantity_remaining)

            if self.quantity_remaining is None and self.quantity_received is not None:
                self.quantity_remaining = int(self.quantity_received)

        if not self._state.adding:
            original = StockBatch.objects.only("quantity_received", "unit_cost").get(
                pk=self.pk
            )

            if self.quantity_received != original.quantity_received:
                raise ValidationError(
                    {"quantity_received": "quantity_received is immutable"}
                )

            if original.unit_cost is not None:
                if self.unit_cost != original.unit_cost:
                    raise ValidationError(
                        {"unit_cost": "unit_cost is immutable once set"}
                    )
            else:
                if self.unit_cost is not None and self.unit_cost <= Decimal("0.00"):
                    raise ValidationError(
                        {"unit_cost": "unit_cost must be greater than zero"}
                    )

        self.is_active = int(self.quantity_remaining or 0) > 0

        self.full_clean()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        from products.models.stock_movement import StockMovement

        if StockMovement.objects.filter(batch=self).exists():
            raise ValidationError(
                "Cannot delete StockBatch: it has StockMovement audit history."
            )
        return super().delete(*args, **kwargs)

    def __str__(self):
        product_name = getattr(self.product, "name", "Product")
        store_name = getattr(getattr(self, "store", None), "name", "NO-STORE")
        return f"{store_name} | {product_name} | Batch {self.batch_number}"
