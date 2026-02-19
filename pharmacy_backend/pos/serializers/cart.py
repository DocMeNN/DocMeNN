"""
PATH: pos/serializers/cart.py

CART SERIALIZER (PHASE 1)

Purpose:
- Return a POS cart in a frontend-friendly shape.
- Keep money + totals server-derived (single source of truth).
- Backward compatible fields for older tests/clients.

Compatibility:
- Tests reference `total_amount` for cart responses.
  In POS, cart total is the cart subtotal (no tax/discount at cart level).
"""

from decimal import Decimal

from rest_framework import serializers

from pos.models import Cart

from .cart_item import CartItemSerializer


class CartSerializer(serializers.ModelSerializer):
    store_id = serializers.UUIDField(source="store.id", read_only=True, allow_null=True)
    store_name = serializers.CharField(source="store.name", read_only=True, default="")

    items = CartItemSerializer(many=True, read_only=True)

    item_count = serializers.SerializerMethodField(read_only=True)
    subtotal_amount = serializers.SerializerMethodField(read_only=True)

    # Backward-compat alias expected by tests
    total_amount = serializers.SerializerMethodField(read_only=True)

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
            "total_amount",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_item_count(self, obj) -> int:
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

        return f"{subtotal:.2f}"

    def get_total_amount(self, obj) -> str:
        # For carts: total == subtotal (no tax/discount at cart level in this module)
        return self.get_subtotal_amount(obj)
