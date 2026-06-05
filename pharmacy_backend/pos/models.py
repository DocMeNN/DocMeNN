# pharmacy_backend/pos/models.py

import uuid
from django.db import models
from django.contrib.auth import get_user_model

from products.models import Product

User = get_user_model()


class POSCart(models.Model):
    """
    Active POS cart per staff user

    DESIGN DECISIONS:
    - One active cart per user (cashier / pharmacist)
    - Cart is ephemeral (cleared after checkout)
    - Stock deduction is NOT handled here
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="pos_cart",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"POS Cart for {self.user}"

    @property
    def total_amount(self):
        """
        Total cart value (computed, not stored)
        """
        total = sum(item.total_price for item in self.items.all())
        return round(total, 2)


class POSCartItem(models.Model):
    """
    Line item inside a POS cart

    IMPORTANT:
    - Price is always derived from Product.unit_price
    - Quantity validation happens at serializer / service level
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    cart = models.ForeignKey(
        POSCart,
        on_delete=models.CASCADE,
        related_name="items",
    )

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="pos_items",
    )

    quantity = models.PositiveIntegerField(
        default=1,
        help_text="Quantity requested by POS user",
    )

    class Meta:
        unique_together = ("cart", "product")
        ordering = ["product__name"]

    def __str__(self):
        return f"{self.product.name} x {self.quantity}"

    @property
    def unit_price(self):
        """
        Snapshot from Product
        """
        return self.product.unit_price

    @property
    def total_price(self):
        """
        Line total
        """
        return self.product.unit_price * self.quantity
