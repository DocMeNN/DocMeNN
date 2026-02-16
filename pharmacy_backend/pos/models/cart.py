# pos/models/cart.py

"""
CART MODEL (PHASE 1)

Purpose:
- Active POS cart (temporary, mutable) — STORE SCOPED.
- Derive subtotal + item count safely from CartItems.

Rules:
- One active cart per user per store
- Converted into Sale at checkout
- Cart is read-only after deactivation
- Store is required for active carts (POS scope)
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
    Active POS cart (temporary, mutable) — STORE SCOPED.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    store = models.ForeignKey(
        Store,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="carts",
        help_text="Store/branch where this cart is created and checked out",
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

    # --------------------------------------------------
    # VALIDATION
    # --------------------------------------------------

    def clean(self):
        # Runtime POS rule: active carts must be store-scoped
        if self.is_active and not self.store_id:
            raise ValidationError({"store": "store is required for an active POS cart"})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    # --------------------------------------------------
    # DERIVED, SAFE READ-ONLY PROPERTIES
    # --------------------------------------------------

    @property
    def item_count(self) -> int:
        """
        Total units in the cart (not line count).

        Example:
        - 2x Paracetamol + 3x Soap => item_count = 5
        """
        total = self.items.aggregate(total=Sum("quantity")).get("total")
        return int(total or 0)

    @property
    def subtotal_amount(self) -> Decimal:
        """
        Safe subtotal calculation.
        """
        total = (
            self.items.annotate(line_total=F("quantity") * F("unit_price"))
            .aggregate(total=Sum("line_total"))
            .get("total")
        )
        return total or Decimal("0.00")

    @property
    def is_empty(self) -> bool:
        return not self.items.exists()

    # --------------------------------------------------
    # STATE GUARDS
    # --------------------------------------------------

    def assert_active(self):
        if not self.is_active:
            raise ValueError("Cart is inactive and cannot be modified")

    def __str__(self):
        status = "ACTIVE" if self.is_active else "CLOSED"
        store_name = getattr(getattr(self, "store", None), "name", "NO-STORE")
        return f"Cart {self.id} | {store_name} | {self.user} | {status}"
