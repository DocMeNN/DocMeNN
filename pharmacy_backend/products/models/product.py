# products/models/product.py

import uuid
from decimal import Decimal, ROUND_HALF_UP

from django.db import models
from django.db.models import Sum
from django.core.exceptions import ValidationError
from django.utils import timezone

from .category import Category
from store.models import Store


class Product(models.Model):
    """
    Represents a sellable product.

    STOCK MODEL (IMPORTANT):
    - Product itself does NOT store stock
    - Stock lives in StockBatch
    - Total stock = sum of NON-EXPIRED, ACTIVE batches

    HOTSPRINT UPGRADE (PURCHASE → MARKUP → SELLING PRICE):
    - Product defines a default markup policy.
    - Purchase intake supplies cost; markup policy yields selling price.
    - unit_price remains the sell price (snapshot at sale time is stored in SaleItem).
    """

    class MarkupType(models.TextChoices):
        PERCENT = "PERCENT", "Percent"
        FIXED = "FIXED", "Fixed Amount"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    store = models.ForeignKey(
        Store,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="products",
    )

    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="products",
    )

    sku = models.CharField(max_length=128, unique=True, db_index=True)
    name = models.CharField(max_length=255, db_index=True)

    # Current/default selling price
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)

    # ✅ Default markup policy (used when stocking/purchasing)
    markup_type = models.CharField(
        max_length=16,
        choices=MarkupType.choices,
        default=MarkupType.PERCENT,
    )

    markup_value = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Percent (e.g. 20.00) if PERCENT; currency amount if FIXED.",
    )

    low_stock_threshold = models.PositiveIntegerField(default=10)

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["sku"]),
            models.Index(fields=["name"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.sku})"

    def clean(self):
        if self.unit_price is None or Decimal(self.unit_price) <= 0:
            raise ValidationError("Unit price must be greater than zero")

        if self.low_stock_threshold is None:
            raise ValidationError("low_stock_threshold is required")

        if self.markup_value is None:
            raise ValidationError("markup_value is required")

        if Decimal(self.markup_value) < Decimal("0.00"):
            raise ValidationError("markup_value cannot be negative")

    def compute_selling_price_from_cost(self, unit_cost) -> Decimal:
        """
        Convert a unit_cost into a selling price based on markup policy.
        This is deterministic and analytics-friendly.
        """
        try:
            cost = Decimal(str(unit_cost))
        except Exception:
            raise ValidationError("unit_cost must be a valid decimal")

        if cost <= Decimal("0.00"):
            raise ValidationError("unit_cost must be greater than zero")

        mv = Decimal(str(self.markup_value or "0.00"))

        if self.markup_type == self.MarkupType.PERCENT:
            # selling = cost * (1 + percent/100)
            selling = cost * (Decimal("1.00") + (mv / Decimal("100.00")))
        else:
            # FIXED markup amount
            selling = cost + mv

        selling = selling.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        if selling <= Decimal("0.00"):
            raise ValidationError("Computed selling price must be greater than zero")

        return selling

    @property
    def total_stock_db(self) -> int:
        """
        Total AVAILABLE stock.

        RULES:
        - Only active batches
        - Only non-expired batches (expiry_date >= today)
        - Sum of quantity_remaining
        """
        today = timezone.localdate()

        return (
            self.stock_batches.filter(is_active=True, expiry_date__gte=today)
            .aggregate(total=Sum("quantity_remaining"))
            .get("total")
            or 0
        )

    @property
    def is_low_stock(self) -> bool:
        return self.total_stock_db <= int(self.low_stock_threshold or 0)
