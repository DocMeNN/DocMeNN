# products/serializers/product.py

"""
PRODUCT SERIALIZER

Purpose:
- Canonical Product serializer for both staff and public storefront.
- Stock is derived from StockBatch only (single source of truth).
- Store-aware stock computation aligns with ProductViewSet rules:
  - If store_id provided: use store batches if they exist; otherwise fall back to NULL-store batches (migration support).
"""

from django.db.models import Sum
from django.utils import timezone
from rest_framework import serializers

from products.models import Category, Product, StockBatch


class ProductSerializer(serializers.ModelSerializer):
    """
    Canonical Product Serializer.

    GUARANTEES:
    - Stock is aggregated from StockBatch (single source of truth)
    - No frontend-side stock math
    - Store-aware (store_id in query params)
    - Migration-safe NULL-store fallback (only if store batches don't exist)
    """

    category = serializers.UUIDField(write_only=True, required=False, allow_null=True)
    category_name = serializers.CharField(source="category.name", read_only=True)

    stock = serializers.SerializerMethodField(read_only=True)
    total_stock = serializers.SerializerMethodField(read_only=True)
    is_low_stock = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Product
        fields = [
            "id",
            "sku",
            "name",
            "store",
            "category",
            "category_name",
            "unit_price",
            "low_stock_threshold",
            "stock",
            "total_stock",
            "is_low_stock",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "category_name",
            "stock",
            "total_stock",
            "is_low_stock",
            "created_at",
            "updated_at",
        ]

    def validate_sku(self, value):
        value = (value or "").strip().upper()
        if not value:
            raise serializers.ValidationError("SKU is required")
        return value

    def validate_unit_price(self, value):
        # Keep consistent with Product.clean(): non-negative (0 allowed)
        if value is None or value < 0:
            raise serializers.ValidationError("Unit price must be non-negative")
        return value

    # -----------------------------
    # STORE CONTEXT (best effort)
    # -----------------------------
    def _ctx_store_id(self):
        req = self.context.get("request")
        if not req:
            return None
        return (req.query_params.get("store_id") or "").strip() or None

    # -----------------------------
    # STOCK (annotation if present; fallback DB compute)
    # -----------------------------
    def _annotated_total_stock(self, obj):
        annotated = getattr(obj, "total_stock", None)
        if annotated is None:
            return None
        try:
            return int(annotated or 0)
        except Exception:
            return 0

    def _compute_total_stock_db(self, obj) -> int:
        """
        Store-aware stock computation aligned with ProductViewSet:
        - If store_id is supplied:
            - Use store batches if any exist (for that product)
            - Else fall back to NULL-store batches
        - If no store_id:
            - sum across all batches
        """
        today = timezone.localdate()
        store_id = self._ctx_store_id() or None

        base = StockBatch.objects.filter(
            product=obj,
            is_active=True,
            expiry_date__gte=today,
            quantity_remaining__gt=0,
        )

        # If StockBatch has store FK, enforce store rules
        try:
            StockBatch._meta.get_field("store")
            has_store_fk = True
        except Exception:
            has_store_fk = False

        if store_id and has_store_fk:
            store_qs = base.filter(store_id=store_id)
            if store_qs.exists():
                total = store_qs.aggregate(total=Sum("quantity_remaining")).get("total")
                return int(total or 0)

            null_qs = base.filter(store__isnull=True)
            total = null_qs.aggregate(total=Sum("quantity_remaining")).get("total")
            return int(total or 0)

        # If no store FK, best-effort: rely on product.store or global
        if store_id and not has_store_fk:
            # If product has store_id and doesn't match requested store, treat as 0 stock for this view
            p_store_id = getattr(obj, "store_id", None)
            if p_store_id and str(p_store_id) != str(store_id):
                return 0

        total = base.aggregate(total=Sum("quantity_remaining")).get("total")
        return int(total or 0)

    def _get_total_stock(self, obj) -> int:
        annotated = self._annotated_total_stock(obj)
        if annotated is not None:
            return annotated
        return self._compute_total_stock_db(obj)

    def get_stock(self, obj):
        return self._get_total_stock(obj)

    def get_total_stock(self, obj):
        return self._get_total_stock(obj)

    def get_is_low_stock(self, obj):
        stock = self._get_total_stock(obj)
        threshold = int(getattr(obj, "low_stock_threshold", 0) or 0)
        return stock <= threshold

    # -----------------------------
    # CREATE / UPDATE
    # -----------------------------
    def create(self, validated_data):
        category_id = validated_data.pop("category", None)

        if category_id:
            try:
                validated_data["category"] = Category.objects.get(id=category_id)
            except Category.DoesNotExist:
                raise serializers.ValidationError({"category": "Invalid category ID"})

        return Product.objects.create(**validated_data)

    def update(self, instance, validated_data):
        category_id = validated_data.pop("category", None)

        if category_id is not None:
            if category_id == "" or category_id is None:
                instance.category = None
            else:
                try:
                    instance.category = Category.objects.get(id=category_id)
                except Category.DoesNotExist:
                    raise serializers.ValidationError({"category": "Invalid category ID"})

        return super().update(instance, validated_data)

    # -----------------------------
    # BULK SUPPORT
    # -----------------------------
    @classmethod
    def many_init(cls, *args, **kwargs):
        class BulkProductListSerializer(serializers.ListSerializer):
            def create(self, validated_data):
                products = []

                for item in validated_data:
                    category_id = item.pop("category", None)

                    if category_id:
                        try:
                            item["category"] = Category.objects.get(id=category_id)
                        except Category.DoesNotExist:
                            raise serializers.ValidationError(
                                {"category": "Invalid category ID"}
                            )

                    products.append(Product(**item))

                return Product.objects.bulk_create(products, ignore_conflicts=True)

        kwargs["child"] = cls()
        return BulkProductListSerializer(*args, **kwargs)