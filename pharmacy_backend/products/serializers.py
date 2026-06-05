from rest_framework import serializers
from django.db import transaction
from django.utils import timezone

from .models import Product, Category, StockBatch


# ============================================================
# CATEGORY
# ============================================================

class CategorySerializer(serializers.ModelSerializer):
    """
    Simple Category serializer (read-only for now)
    """

    class Meta:
        model = Category
        fields = ["id", "name"]


# ============================================================
# STOCK BATCH (RECEIVING / INVENTORY)
# ============================================================

class StockBatchSerializer(serializers.ModelSerializer):
    """
    Serializer for inventory stock batches

    Used for:
    - Stock receiving
    - Inventory listing
    - Analytics

    IMPORTANT:
    - quantity_remaining initialized from quantity_received
    - FIFO handled in service layer
    """

    # Input
    product_id = serializers.UUIDField(write_only=True)

    # Output
    product = serializers.CharField(
        source="product.name",
        read_only=True,
    )

    class Meta:
        model = StockBatch
        fields = [
            "id",
            "product",
            "product_id",
            "batch_number",
            "expiry_date",
            "quantity_received",
            "quantity_remaining",
            "is_active",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "quantity_remaining",
            "is_active",
            "created_at",
        ]

    # --------------------
    # VALIDATIONS
    # --------------------
    def validate_quantity_received(self, value):
        if value <= 0:
            raise serializers.ValidationError(
                "Quantity received must be greater than zero"
            )
        return value

    def validate_expiry_date(self, value):
        if value < timezone.now().date():
            raise serializers.ValidationError(
                "Expiry date cannot be in the past"
            )
        return value

    # --------------------
    # CREATE
    # --------------------
    @transaction.atomic
    def create(self, validated_data):
        product_id = validated_data.pop("product_id")

        try:
            product = Product.objects.get(id=product_id, is_active=True)
        except Product.DoesNotExist:
            raise serializers.ValidationError(
                {"product_id": "Invalid or inactive product ID"}
            )

        validated_data["product"] = product
        validated_data["quantity_remaining"] = validated_data["quantity_received"]

        return StockBatch.objects.create(**validated_data)


# ============================================================
# PRODUCT
# ============================================================

class ProductSerializer(serializers.ModelSerializer):
    """
    Canonical Product Serializer

    Used for:
    - Create / Update
    - List / Retrieve
    - Bulk create (JSON & CSV)
    """

    # -------- CATEGORY --------
    category_id = serializers.UUIDField(
        write_only=True,
        required=False,
        allow_null=True,
    )

    category = serializers.CharField(
        source="category.name",
        read_only=True,
    )

    # -------- INVENTORY --------
    total_stock = serializers.IntegerField(read_only=True)

    class Meta:
        model = Product
        fields = [
            "id",
            "sku",
            "name",
            "category",
            "category_id",
            "unit_price",
            "low_stock_threshold",
            "total_stock",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "total_stock",
            "created_at",
            "updated_at",
        ]

    # -------------------------
    # VALIDATIONS
    # -------------------------
    def validate_sku(self, value):
        value = value.strip().upper()
        if not value:
            raise serializers.ValidationError("SKU is required")
        return value

    def validate_unit_price(self, value):
        if value <= 0:
            raise serializers.ValidationError(
                "Unit price must be greater than zero"
            )
        return value

    # -------------------------
    # CREATE / UPDATE
    # -------------------------
    def create(self, validated_data):
        category_id = validated_data.pop("category_id", None)

        if category_id:
            try:
                validated_data["category"] = Category.objects.get(id=category_id)
            except Category.DoesNotExist:
                raise serializers.ValidationError(
                    {"category_id": "Invalid category ID"}
                )

        return Product.objects.create(**validated_data)

    def update(self, instance, validated_data):
        category_id = validated_data.pop("category_id", None)

        if category_id is not None:
            try:
                instance.category = Category.objects.get(id=category_id)
            except Category.DoesNotExist:
                raise serializers.ValidationError(
                    {"category_id": "Invalid category ID"}
                )

        return super().update(instance, validated_data)

    # -------------------------
    # BULK CREATE (OPTIMIZED)
    # -------------------------
    @classmethod
    def many_init(cls, *args, **kwargs):

        class BulkProductListSerializer(serializers.ListSerializer):
            @transaction.atomic
            def create(self, validated_data):
                products = []

                for item in validated_data:
                    category_id = item.pop("category_id", None)

                    if category_id:
                        try:
                            item["category"] = Category.objects.get(id=category_id)
                        except Category.DoesNotExist:
                            raise serializers.ValidationError(
                                {"category_id": "Invalid category ID"}
                            )

                    products.append(Product(**item))

                return Product.objects.bulk_create(
                    products,
                    ignore_conflicts=True,
                )

        kwargs["child"] = cls()
        return BulkProductListSerializer(*args, **kwargs)
