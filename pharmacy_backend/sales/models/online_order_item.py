# sales/models/online_order_item.py

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models

from products.models import Product


class OnlineOrderItem(models.Model):
    """
    Line items for OnlineOrder.
    """

    order = models.ForeignKey(
        "sales.OnlineOrder",
        on_delete=models.CASCADE,
        related_name="items",
    )

    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name="online_order_items",
    )

    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    unit_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )

    total_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
        help_text="quantity * unit_price (server computed)",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["created_at"]),
            models.Index(fields=["order"]),
            models.Index(fields=["product"]),
        ]

    def clean(self):
        if self.quantity is None or int(self.quantity) <= 0:
            raise ValidationError("quantity must be >= 1")

        if self.unit_price is None or Decimal(self.unit_price) <= Decimal("0.00"):
            raise ValidationError("unit_price must be > 0")

        expected = (Decimal(self.quantity) * Decimal(self.unit_price)).quantize(
            Decimal("0.01")
        )
        self.total_price = expected

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.product} x{self.quantity}"
