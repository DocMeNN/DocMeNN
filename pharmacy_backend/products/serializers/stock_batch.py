# products/serializers/stock_batch.py
"""
======================================================
PATH: products/serializers/stock_batch.py
======================================================
STOCK BATCH SERIALIZER (PHASE 2)

Purpose:
- Validate StockBatch inputs for the ViewSet boundary.
- Keep quantity mutations service-managed.
- Enforce purchase-led intake rules (unit_cost required on create).

Key Fix (Frontend Compatibility):
- Accepts BOTH "product_id" and "productId" on POST.
- batch_number is OPTIONAL on POST.
  If missing/blank -> normalize to None so intake_stock() auto-generates.

IMPORTANT (AUDIT + BEST PRACTICE):
- unit_cost is NEVER PATCH-able via API.
  If legacy batches exist with missing unit_cost, backfill must happen via:
  - management command, or
  - admin-only controlled data migration
"""

from __future__ import annotations

from decimal import Decimal

from django.utils import timezone
from rest_framework import serializers

from products.models import Product, StockBatch


class StockBatchSerializer(serializers.ModelSerializer):
    # IMPORTANT: Model has blank=False, so DRF would make this required by default.
    # We override to make it optional for purchase-led intake.
    batch_number = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
        help_text="Supplier / delivery batch reference (optional; auto-generated if missing).",
    )

    # Canonical input (backend)
    product_id = serializers.UUIDField(write_only=True, required=False)
    # Frontend alias (React commonly sends productId)
    productId = serializers.UUIDField(write_only=True, required=False)

    product = serializers.CharField(source="product.name", read_only=True)
    product_uuid = serializers.UUIDField(source="product.id", read_only=True)

    unit_cost = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=False,  # enforced on create in validate()
        allow_null=True,  # supports legacy rows already in DB
    )

    class Meta:
        model = StockBatch
        fields = [
            "id",
            "product",
            "product_uuid",
            "product_id",
            "productId",
            "batch_number",
            "expiry_date",
            "quantity_received",
            "quantity_remaining",
            "unit_cost",
            "is_active",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "product",
            "product_uuid",
            "quantity_remaining",
            "is_active",
            "created_at",
        ]

    def validate_quantity_received(self, value):
        if value is None:
            raise serializers.ValidationError("quantity_received is required")
        try:
            v = int(value)
        except Exception:
            raise serializers.ValidationError("quantity_received must be an integer")
        if v <= 0:
            raise serializers.ValidationError("quantity_received must be greater than zero")
        return v

    def validate_expiry_date(self, value):
        if value is None:
            raise serializers.ValidationError("expiry_date is required")
        if value < timezone.localdate():
            raise serializers.ValidationError("expiry_date cannot be in the past")
        return value

    def _coerce_unit_cost(self, raw):
        if raw in (None, "", "null"):
            return None
        try:
            return Decimal(str(raw))
        except Exception:
            raise serializers.ValidationError(
                {"unit_cost": "unit_cost must be a valid decimal value"}
            )

    def _normalize_batch_number(self, raw):
        """
        batch_number is OPTIONAL on create.
        - missing / None / "" / "   " -> None
        - "  ABC  " -> "ABC"
        """
        if raw is None:
            return None
        bn = str(raw).strip()
        return bn or None

    def _resolve_product_id(self, attrs) -> object | None:
        """
        Accept both:
        - product_id (canonical)
        - productId (frontend alias)
        """
        pid = attrs.get("product_id", None)
        if pid:
            return pid
        pid2 = attrs.get("productId", None)
        if pid2:
            attrs["product_id"] = pid2
            return pid2
        return None

    def validate(self, attrs):
        is_update = self.instance is not None

        # PATCH rules
        if is_update:
            forbidden = {
                "quantity_received",
                "quantity_remaining",
                "is_active",
                "product",
                "product_id",
                "productId",
                "unit_cost",  # locked via API
            }
            incoming = set(attrs.keys())
            bad = sorted(list(incoming.intersection(forbidden)))
            if bad:
                raise serializers.ValidationError(
                    {
                        "detail": (
                            f"Field(s) {bad} cannot be edited directly. "
                            "Use actions/services for controlled ops."
                        )
                    }
                )

            if "batch_number" in attrs:
                bn = (attrs.get("batch_number") or "").strip()
                if not bn:
                    raise serializers.ValidationError(
                        {"batch_number": "batch_number cannot be blank"}
                    )
                attrs["batch_number"] = bn

            return attrs

        # POST rules
        # product_id required (but allow alias productId)
        product_id = self._resolve_product_id(attrs)
        if not product_id:
            raise serializers.ValidationError({"product_id": "product_id is required"})

        # batch_number optional: normalize to None so service generates it
        attrs["batch_number"] = self._normalize_batch_number(attrs.get("batch_number", None))

        unit_cost = self._coerce_unit_cost(attrs.get("unit_cost"))
        if unit_cost is None:
            raise serializers.ValidationError(
                {"unit_cost": "unit_cost is required (purchase-led stock intake)."}
            )
        if unit_cost <= Decimal("0.00"):
            raise serializers.ValidationError(
                {"unit_cost": "unit_cost must be greater than zero"}
            )
        attrs["unit_cost"] = unit_cost

        return attrs

    def create(self, validated_data):
        """
        NOTE:
        - ViewSet.create() uses intake_stock() as the canonical create path.
        - This create() remains safe if used anywhere else accidentally.
        """
        # Support alias field if it somehow survived validation
        validated_data.pop("productId", None)

        product_id = validated_data.pop("product_id")
        try:
            product = Product.objects.get(id=product_id, is_active=True)
        except Product.DoesNotExist:
            raise serializers.ValidationError(
                {"product_id": "Invalid or inactive product ID"}
            )

        batch = StockBatch.objects.create(
            product=product,
            quantity_remaining=0,
            **validated_data,
        )
        return batch

    def update(self, instance, validated_data):
        # Alias not applicable on PATCH
        validated_data.pop("productId", None)

        if "batch_number" in validated_data:
            instance.batch_number = (validated_data["batch_number"] or "").strip()

        if "expiry_date" in validated_data:
            instance.expiry_date = validated_data["expiry_date"]

        instance.save()
        return instance