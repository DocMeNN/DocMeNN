"""
PATH: pos/serializers/cart_item.py

CART ITEM SERIALIZER (PHASE 1)

Purpose:
- Serialize cart line items for POS UI.
- unit_price is read-only (server-controlled snapshot).
- Provide stable fields for frontend wiring (product_id, product_name).
"""

from rest_framework import serializers

from pos.models import CartItem


class CartItemSerializer(serializers.ModelSerializer):
    product_id = serializers.UUIDField(source="product.id", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)

    unit_price = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        read_only=True,
    )

    line_total = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        read_only=True,
    )

    class Meta:
        model = CartItem
        fields = [
            "id",
            "product_id",
            "product_name",
            "quantity",
            "unit_price",
            "line_total",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "product_id",
            "product_name",
            "unit_price",
            "line_total",
            "created_at",
        ]

    def validate_quantity(self, value):
        try:
            v = int(value)
        except (TypeError, ValueError):
            raise serializers.ValidationError("quantity must be an integer")
        if v <= 0:
            raise serializers.ValidationError("quantity must be greater than zero")
        return v
