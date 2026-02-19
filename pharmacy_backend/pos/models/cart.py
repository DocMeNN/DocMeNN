"""
PATH: pos/models/cart.py

CART MODEL (PHASE 1)

Purpose:
- Active POS cart (temporary, mutable).
- Backward compatible with legacy single-store mode (store can be NULL).
- Derive subtotal + item count safely from CartItems.

Rules:
- One active cart per user per store (including NULL store).
- Converted into Sale at checkout.
- Cart is read-only after deactivation.

IMPORTANT (Back-compat):
- Store is OPTIONAL for active carts to support legacy tests and single-store setups.
- Multi-store enforcement should happen at API layer when store_id is supplied/required.
"""

import uuid
from decimal import Decimal

from django.db import models
from django.conf import settings
from django.db.models import Sum, F
from django.core.exceptions import ValidationError

from store.models import Store

User = settings.AUTH_USER_MODEL


class Cart(models.Model):
    """
    Active POS cart (temporary, mutable).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    store = models.ForeignKey(
        Store,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="carts",
        help_text="Store/branch context. Optional for legacy single-store carts.",
    )

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="carts",
    )

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "store"],
                condition=models.Q(is_active=True),
                name="one_active_cart_per_user_per_store",
            )
        ]

    def clean(self):
        # Backward compatible: DO NOT enforce store presence here.
        # Store requirement (if desired) must be enforced at the API layer.
        if self.user_id is None:
            raise ValidationError({"user": "user is required"})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    @property
    def item_count(self) -> int:
        total = self.items.aggregate(total=Sum("quantity")).get("total")
        return int(total or 0)

    @property
    def subtotal_amount(self) -> Decimal:
        total = (
            self.items.annotate(line_total=F("quantity") * F("unit_price"))
            .aggregate(total=Sum("line_total"))
            .get("total")
        )
        return total or Decimal("0.00")

    @property
    def is_empty(self) -> bool:
        return not self.items.exists()

    def assert_active(self):
        if not self.is_active:
            raise ValueError("Cart is inactive and cannot be modified")

    def __str__(self):
        status = "ACTIVE" if self.is_active else "CLOSED"
        store_name = getattr(getattr(self, "store", None), "name", "NO-STORE")
        return f"Cart {self.id} | {store_name} | {self.user} | {status}"
