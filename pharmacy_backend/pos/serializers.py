# pharmacy_backend/pos/serializers.py

from rest_framework import serializers

from .models import POSCart, POSCartItem


# =====================================================
# POS CART ITEM
# =====================================================

class POSCartItemSerializer(serializers.ModelSerializer):
    """
    Serializer for POS cart line items

    RESPONSIBILITIES:
    - Display product info
    - Validate quantity
    - Compute pricing (read-only)
    """

    # -------- PRODUCT INFO (READ-ONLY) --------
    product_name = serializers.CharField(
        source="product.name",
        read_only=True,
    )

    unit_price = serializers.DecimalField(
        source="product.unit_price",
        max_digits=10,
        decimal_places=2,
        read_only=True,
    )

    total_price = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        read_only=True,
    )

    class Meta:
        model = POSCartItem
        fields = [
            "id",
            "product",
            "product_name",
            "quantity",
            "unit_price",
            "total_price",
        ]
        read_only_fields = [
            "id",
            "product_name",
            "unit_price",
            "total_price",
        ]

    def validate_quantity(self, value):
        if value <= 0:
            raise serializers.ValidationError(
                "Quantity must be greater than zero"
            )
        return value


# =====================================================
# POS CART
# =====================================================

class POSCartSerializer(serializers.ModelSerializer):
    """
    Serializer for POS cart

    NOTES:
    - Uses __all__ to avoid schema crashes
    - Nested cart items are read-only
    - Swagger-safe
    """

    items = POSCartItemSerializer(
        many=True,
        read_only=True,
    )

    class Meta:
        model = POSCart
        fields = "__all__"
