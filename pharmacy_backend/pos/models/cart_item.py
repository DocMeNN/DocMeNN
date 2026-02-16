# pos/models/cart_item.py

"""
CART ITEM MODEL (PHASE 1)

Purpose:
- Store POS cart line items.
- Unit price is a snapshot at time of add (server-controlled).
- Quantity is integer-only and validated.

Rules:
- One product per cart (DB constraint).
- Quantity must be > 0.
- Unit price must be > 0.
"""

import uuid
from decimal import Decimal

from django.db import models
from django.core.exceptions import ValidationError

from products.models import Product
from .cart import Cart


class CartItem(models.Model):
    """
    Individual line item in a POS cart.

    RULES:
    - Created ONLY via POS API
    - One product per cart
    - Unit price is SNAPSHOT at time of add (server-controlled)
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    cart = models.ForeignKey(
        Cart,
        on_delete=models.CASCADE,
        related_name="items",
    )

    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name="cart_items",
    )

    quantity = models.PositiveIntegerField(help_text="Must be greater than zero")

    unit_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Snapshot price at time of adding to cart (server-controlled)",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["cart", "product"],
                name="unique_product_per_cart",
            )
        ]

    def clean(self):
        if self.quantity is None or int(self.quantity) <= 0:
            raise ValidationError({"quantity": "Quantity must be greater than zero"})

        if self.unit_price is None or self.unit_price <= 0:
            raise ValidationError({"unit_price": "Unit price must be greater than zero"})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    @property
    def line_total(self) -> Decimal:
        # Decimal * int is safe here
        return (self.unit_price or Decimal("0.00")) * Decimal(int(self.quantity or 0))

    def __str__(self):
        return f"{getattr(self.product, 'name', 'Product')} x {self.quantity}"
