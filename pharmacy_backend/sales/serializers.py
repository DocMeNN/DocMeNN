# pharmacy_backend/sales/serializers.py

from decimal import Decimal

from django.db import transaction
from rest_framework import serializers

from sales.models import Sale, SaleItem
from products.models import Product
from products.services.stock_fifo import deduct_stock_fifo


# ======================================================================
# SALE ITEM SERIALIZER
# ======================================================================

class SaleItemSerializer(serializers.ModelSerializer):
    """
    Line item serializer used during POS checkout.
    """

    product = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.all()
    )

    class Meta:
        model = SaleItem
        fields = [
            "id",
            "product",
            "batch_reference",
            "quantity",
            "unit_price",
            "total_price",
        ]
        read_only_fields = [
            "id",
            "total_price",
        ]

    # -------------------- VALIDATIONS --------------------

    def validate_quantity(self, value):
        if value <= 0:
            raise serializers.ValidationError(
                "Quantity must be greater than zero."
            )
        return value

    def validate_unit_price(self, value):
        if value <= 0:
            raise serializers.ValidationError(
                "Unit price must be greater than zero."
            )
        return value


# ======================================================================
# SALE SERIALIZER (CREATE + READ)
# ======================================================================

class SaleSerializer(serializers.ModelSerializer):
    """
    Handles:
    - POS checkout (create)
    - Sale read / reporting
    """

    items = SaleItemSerializer(many=True)
    user = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = Sale
        fields = [
            "id",
            "invoice_no",
            "user",
            "subtotal_amount",
            "tax_amount",
            "discount_amount",
            "total_amount",
            "payment_method",
            "status",
            "created_at",
            "completed_at",
            "items",
        ]
        read_only_fields = [
            "id",
            "invoice_no",
            "created_at",
            "completed_at",
            "subtotal_amount",
            "total_amount",
        ]

    # --------------------------------------------------
    # VALIDATION
    # --------------------------------------------------

    def validate_items(self, value):
        if not value:
            raise serializers.ValidationError(
                "A sale must contain at least one item."
            )
        return value

    # --------------------------------------------------
    # CREATE (POS TRANSACTION)
    # --------------------------------------------------

    @transaction.atomic
    def create(self, validated_data):
        """
        Creates:
        - Sale header
        - Sale items
        - FIFO stock deduction (single source of truth)

        This is the ONLY place stock is reduced for sales.
        """

        items_data = validated_data.pop("items")
        request = self.context.get("request")
        user = request.user if request else None

        # Create sale header (amounts computed later)
        sale = Sale.objects.create(
            user=user,
            subtotal_amount=Decimal("0.00"),
            total_amount=Decimal("0.00"),
            **validated_data,
        )

        subtotal = Decimal("0.00")

        # --------------------
        # LINE ITEMS + FIFO
        # --------------------
        for item_data in items_data:
            product = item_data["product"]
            quantity = item_data["quantity"]
            unit_price = item_data["unit_price"]

            sale_item = SaleItem.objects.create(
                sale=sale,
                product=product,
                quantity=quantity,
                unit_price=unit_price,
            )

            subtotal += sale_item.total_price

            # 🔥 FIFO STOCK DEDUCTION (AUDIT SAFE)
            deduct_stock_fifo(
                product=product,
                quantity=quantity,
                user=user,
                sale=sale,
            )

        # --------------------
        # FINAL TOTALS
        # --------------------
        sale.subtotal_amount = subtotal
        sale.total_amount = (
            subtotal
            + sale.tax_amount
            - sale.discount_amount
        )

        sale.save(
            update_fields=[
                "subtotal_amount",
                "total_amount",
            ]
        )

        return sale
