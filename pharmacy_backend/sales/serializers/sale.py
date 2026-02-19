# sales/serializers/sale.py

from django.db.models import DecimalField, F, Sum
from django.db.models.expressions import ExpressionWrapper
from rest_framework import serializers

from sales.models import Sale
from sales.models.refund_audit import SaleRefundAudit
from sales.models.sale_item import SaleItem
from sales.models.sale_item_refund import SaleItemRefund
from sales.models.sale_payment_allocation import SalePaymentAllocation


class SaleRefundAuditSerializer(serializers.ModelSerializer):
    class Meta:
        model = SaleRefundAudit
        fields = [
            "id",
            "refunded_by",
            "reason",
            "refunded_at",
            "original_total_amount",
        ]
        read_only_fields = fields


class SalePaymentAllocationSerializer(serializers.ModelSerializer):
    """
    Split payment legs (read-only).
    Returned on receipts and sales history when payment_method == "split".
    """

    class Meta:
        model = SalePaymentAllocation
        fields = [
            "id",
            "method",
            "amount",
            "reference",
            "note",
            "created_at",
        ]
        read_only_fields = fields


class SaleItemSerializer(serializers.ModelSerializer):
    """
    Sale line item serializer (read-only).
    Designed for receipts + UI display.
    """

    product_name = serializers.SerializerMethodField()
    sku = serializers.SerializerMethodField()
    barcode = serializers.SerializerMethodField()

    class Meta:
        model = SaleItem
        fields = [
            "id",
            "product",
            "product_name",
            "sku",
            "barcode",
            "batch_reference",
            "quantity",
            "unit_price",
            "total_price",
        ]
        read_only_fields = fields

    def get_product_name(self, obj):
        p = getattr(obj, "product", None)
        return getattr(p, "name", None) or "Item"

    def get_sku(self, obj):
        p = getattr(obj, "product", None)
        return getattr(p, "sku", None)

    def get_barcode(self, obj):
        p = getattr(obj, "product", None)
        return getattr(p, "barcode", None)


class SaleSerializer(serializers.ModelSerializer):
    """
    CANONICAL SALE SERIALIZER

    NOTE:
    - customer_name is serializer-only (non-persistent)
    - Used for receipts / UI display

    PARTIAL REFUND VISIBILITY (UI SUPPORT):
    - Partial refunds are append-only events (SaleItemRefund).
    - A sale may remain COMPLETED while having partial refunds.
    - These fields let Sales History show refund activity even without refund_audit:

        partial_refund_count
        partial_refund_qty_total
        partial_refund_amount_total
        partial_refund_last_at
        is_partially_refunded
        refunded_amount_total   (partial total + full audit total if present)

    Performance note:
    - We cache aggregates per sale object inside this serializer instance.
    - If needed, we can later optimize further by annotating in the queryset.
    """

    customer_name = serializers.CharField(
        required=False,
        allow_blank=True,
        write_only=True,
        help_text="Optional walk-in customer name (not persisted)",
    )

    # ✅ include store id for UI routing (/pos/:storeId/receipt/:saleId)
    store_id = serializers.SerializerMethodField()

    items = SaleItemSerializer(many=True, read_only=True)
    refund_audit = SaleRefundAuditSerializer(read_only=True)

    # ✅ split payment legs (read-only)
    payment_allocations = SalePaymentAllocationSerializer(many=True, read_only=True)

    # ✅ Partial refund visibility fields
    partial_refund_count = serializers.SerializerMethodField()
    partial_refund_qty_total = serializers.SerializerMethodField()
    partial_refund_amount_total = serializers.SerializerMethodField()
    partial_refund_last_at = serializers.SerializerMethodField()
    is_partially_refunded = serializers.SerializerMethodField()
    refunded_amount_total = serializers.SerializerMethodField()

    class Meta:
        model = Sale
        fields = [
            "id",
            "invoice_no",
            "user",
            "store_id",
            "customer_name",
            "subtotal_amount",
            "tax_amount",
            "discount_amount",
            "total_amount",
            "payment_method",
            "status",
            "created_at",
            "completed_at",
            "items",
            "payment_allocations",
            "refund_audit",
            # partial refund visibility
            "partial_refund_count",
            "partial_refund_qty_total",
            "partial_refund_amount_total",
            "partial_refund_last_at",
            "is_partially_refunded",
            "refunded_amount_total",
        ]
        read_only_fields = [
            "id",
            "invoice_no",
            "user",
            "store_id",
            "created_at",
            "completed_at",
            "items",
            "payment_allocations",
            "refund_audit",
            "partial_refund_count",
            "partial_refund_qty_total",
            "partial_refund_amount_total",
            "partial_refund_last_at",
            "is_partially_refunded",
            "refunded_amount_total",
        ]

    def create(self, validated_data):
        validated_data.pop("customer_name", None)
        return super().create(validated_data)

    # ------------------------------------------------------
    # Store id helper
    # ------------------------------------------------------

    def get_store_id(self, obj: Sale):
        sid = getattr(obj, "store_id", None)
        if sid:
            return str(sid)
        store = getattr(obj, "store", None)
        if store is not None:
            return str(getattr(store, "id", "")) or None
        return None

    # ------------------------------------------------------
    # Partial refund helpers (cached)
    # ------------------------------------------------------

    def _partial_refund_queryset(self, sale: Sale):
        return SaleItemRefund.objects.filter(sale=sale)

    def _partial_refund_aggregates_cached(self, sale: Sale) -> dict:
        """
        Returns cached aggregates:
          count, qty_total, amount_total, last_at

        amount_total = SUM(unit_price_snapshot * quantity_refunded)
        """
        if not hasattr(self, "_partial_refund_cache"):
            self._partial_refund_cache = {}

        key = str(getattr(sale, "id", "") or "")
        if key and key in self._partial_refund_cache:
            return self._partial_refund_cache[key]

        qs = self._partial_refund_queryset(sale)

        line_total_expr = ExpressionWrapper(
            F("unit_price_snapshot") * F("quantity_refunded"),
            output_field=DecimalField(max_digits=18, decimal_places=2),
        )

        agg = qs.aggregate(
            qty_total=Sum("quantity_refunded"),
            amount_total=Sum(line_total_expr),
        )

        last = qs.order_by("-refunded_at").values("refunded_at").first()

        out = {
            "count": int(qs.count()),
            "qty_total": int(agg.get("qty_total") or 0),
            "amount_total": agg.get("amount_total") or 0,
            "last_at": last.get("refunded_at") if last else None,
            "exists": qs.exists(),
        }

        if key:
            self._partial_refund_cache[key] = out

        return out

    def get_partial_refund_count(self, obj: Sale) -> int:
        return int(self._partial_refund_aggregates_cached(obj).get("count") or 0)

    def get_partial_refund_qty_total(self, obj: Sale) -> int:
        return int(self._partial_refund_aggregates_cached(obj).get("qty_total") or 0)

    def get_partial_refund_amount_total(self, obj: Sale):
        return self._partial_refund_aggregates_cached(obj).get("amount_total") or 0

    def get_partial_refund_last_at(self, obj: Sale):
        return self._partial_refund_aggregates_cached(obj).get("last_at")

    def get_is_partially_refunded(self, obj: Sale) -> bool:
        # If full refund audit exists, it's not "partial" anymore.
        if getattr(obj, "refund_audit", None) is not None:
            return False
        return bool(self._partial_refund_aggregates_cached(obj).get("exists"))

    def get_refunded_amount_total(self, obj: Sale):
        """
        Total refunded amount seen by the UI:
        - includes partial refunds sum (unit_price_snapshot * qty)
        - includes full refund audit amount (if present)
        """
        partial_total = self.get_partial_refund_amount_total(obj) or 0

        audit = getattr(obj, "refund_audit", None)
        if audit is None:
            return partial_total

        audit_amount = (
            getattr(audit, "original_total_amount", None)
            or getattr(audit, "total_amount", None)
            or getattr(audit, "amount", None)
            or 0
        )

        try:
            return partial_total + audit_amount
        except Exception:
            return audit_amount or partial_total
