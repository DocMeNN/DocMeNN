# pos/serializers/cart.py

"""
CART SERIALIZER (PHASE 1)

Purpose:
- Return a POS cart in a frontend-friendly shape.
- Keep money + totals server-derived (single source of truth).
- Include store context for multi-store POS operations.
"""

from decimal import Decimal

from rest_framework import serializers

from pos.models import Cart
from .cart_item import CartItemSerializer


class CartSerializer(serializers.ModelSerializer):
    """
    Serializer for POS cart.

    Guarantees:
    - items are read-only
    - totals are computed server-side (never trusted from client)
    - store context is included
    """

    store_id = serializers.UUIDField(source="store.id", read_only=True)
    store_name = serializers.CharField(source="store.name", read_only=True)

    items = CartItemSerializer(many=True, read_only=True)

    item_count = serializers.SerializerMethodField(read_only=True)
    subtotal_amount = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Cart
        fields = [
            "id",
            "store_id",
            "store_name",
            "user",
            "is_active",
            "items",
            "item_count",
            "subtotal_amount",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_item_count(self, obj) -> int:
        # Count total units across lines (better for POS than "number of lines")
        items = getattr(obj, "items", None)
        if not items:
            return 0
        try:
            return sum(int(getattr(i, "quantity", 0) or 0) for i in items.all())
        except Exception:
            return 0

    def get_subtotal_amount(self, obj) -> str:
        items = getattr(obj, "items", None)
        if not items:
            return "0.00"

        subtotal = Decimal("0.00")
        try:
            for i in items.all():
                subtotal += Decimal(str(getattr(i, "line_total", 0) or 0))
        except Exception:
            subtotal = Decimal("0.00")

        # Return as string to avoid float serialization issues
        return f"{subtotal:.2f}"
