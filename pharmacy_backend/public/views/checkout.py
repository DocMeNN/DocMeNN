# public/views/checkout.py
"""
PUBLIC CHECKOUT (ONLINE STORE) — LEGACY V1

⚠️ IMPORTANT (Phase 4):
This endpoint creates a Sale immediately and is NOT payment-gateway safe.
It is kept for:
- cash on delivery
- manual transfer confirmation
- internal testing

For card/Paystack payments, use:
- POST /api/public/order/initiate/
- POST /api/public/payments/paystack/webhook/

Security hardening:
- Throttle (public_write) because it's a write endpoint (abuse target)
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import serializers, status
from rest_framework.parsers import JSONParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from accounting.services.exceptions import (
    AccountResolutionError,
    IdempotencyError,
    JournalEntryCreationError,
)
from accounting.services.posting import post_sale_to_ledger
from products.models import Product
from products.services.stock_fifo import InsufficientStockError, deduct_stock_fifo
from public.serializers import PublicCartItemSerializer
from sales.models import Sale, SaleItem, SalePaymentAllocation
from sales.serializers.sale import SaleSerializer
from store.models import Store

TWOPLACES = Decimal("0.01")


class PublicWriteThrottle(AnonRateThrottle):
    scope = "public_write"


def _money(v) -> Decimal:
    if v is None or v == "":
        return Decimal("0.00")
    return Decimal(str(v)).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def _to_int_qty(value) -> int:
    if value is None or value == "":
        return 0
    if isinstance(value, bool):
        raise ValueError("quantity must be a whole integer unit")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        s = value.strip()
        if s.isdigit():
            return int(s)
    raise ValueError("quantity must be a whole integer unit")


def _normalize_payment_method(method: str | None) -> str:
    m = (method or "online").strip().lower()
    return m or "online"


def _validate_and_normalize_allocations(allocations) -> list[dict]:
    if not allocations:
        return []

    out = []
    for idx, a in enumerate(allocations):
        method = str(a.get("method", "")).strip().lower()
        if method not in {"cash", "bank", "pos", "transfer", "credit"}:
            raise serializers.ValidationError(
                {"payment_allocations": [f"Invalid method at index {idx}: {method}"]}
            )

        amt = _money(a.get("amount", None))
        if amt <= Decimal("0.00"):
            raise serializers.ValidationError(
                {"payment_allocations": [f"Invalid amount at index {idx}: {amt}"]}
            )

        out.append(
            {
                "method": method,
                "amount": amt,
                "reference": str(a.get("reference", "") or "").strip(),
                "note": str(a.get("note", "") or "").strip(),
            }
        )

    return out


class PublicPaymentAllocationSerializer(serializers.Serializer):
    method = serializers.ChoiceField(
        choices=["cash", "bank", "pos", "transfer", "credit"]
    )
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    reference = serializers.CharField(required=False, allow_blank=True, default="")
    note = serializers.CharField(required=False, allow_blank=True, default="")


class PublicCheckoutInputSerializer(serializers.Serializer):
    store_id = serializers.UUIDField()

    customer_name = serializers.CharField(
        required=False, allow_blank=True, allow_null=True
    )
    customer_phone = serializers.CharField(
        required=False, allow_blank=True, allow_null=True
    )
    customer_email = serializers.EmailField(
        required=False, allow_blank=True, allow_null=True
    )

    payment_method = serializers.CharField(
        required=False, allow_blank=True, allow_null=True, default="online"
    )
    items = PublicCartItemSerializer(many=True)

    payment_allocations = PublicPaymentAllocationSerializer(many=True, required=False)


class PublicReceiptItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)

    class Meta:
        model = SaleItem
        fields = [
            "id",
            "product_id",
            "product_name",
            "quantity",
            "unit_price",
            "total_price",
        ]
        read_only_fields = fields


class PublicCheckoutView(APIView):
    permission_classes = [AllowAny]
    parser_classes = [JSONParser]
    throttle_classes = [PublicWriteThrottle]

    @extend_schema(
        request=PublicCheckoutInputSerializer,
        responses={
            201: SaleSerializer,
            400: OpenApiResponse(description="Bad request / validation error"),
            409: OpenApiResponse(description="Stock validation conflict"),
            429: OpenApiResponse(description="Rate limited"),
        },
        description=(
            "LEGACY public checkout (AllowAny). Creates Sale immediately. "
            "Not safe for card gateway payments. Use /order/initiate/ + webhook instead."
        ),
        tags=["Public"],
    )
    @transaction.atomic
    def post(self, request):
        s = PublicCheckoutInputSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        data = s.validated_data

        store = get_object_or_404(Store, id=data["store_id"], is_active=True)

        items = data.get("items") or []
        if not items:
            return Response(
                {"detail": "Cart is empty"}, status=status.HTTP_400_BAD_REQUEST
            )

        actor_user = (
            request.user
            if getattr(request, "user", None) and request.user.is_authenticated
            else None
        )

        normalized_allocs = _validate_and_normalize_allocations(
            data.get("payment_allocations")
        )

        payment_method = _normalize_payment_method(data.get("payment_method"))
        if normalized_allocs:
            payment_method = "split"

        sale_kwargs = dict(
            user=actor_user,
            payment_method=payment_method,
            status=Sale.STATUS_DRAFT,
            subtotal_amount=Decimal("0.00"),
            tax_amount=Decimal("0.00"),
            discount_amount=Decimal("0.00"),
            total_amount=Decimal("0.00"),
        )

        if hasattr(Sale, "store_id"):
            sale_kwargs["store_id"] = store.id
        elif hasattr(Sale, "store"):
            sale_kwargs["store"] = store

        sale = Sale.objects.create(**sale_kwargs)

        subtotal = Decimal("0.00")

        try:
            for line in items:
                product = get_object_or_404(
                    Product, id=line["product_id"], is_active=True
                )

                p_store_id = getattr(product, "store_id", None)
                if p_store_id and p_store_id != store.id:
                    raise serializers.ValidationError(
                        "Product belongs to a different store."
                    )

                qty = _to_int_qty(line["quantity"])
                if qty <= 0:
                    raise serializers.ValidationError("quantity must be >= 1")

                unit_price = _money(getattr(product, "unit_price", None))

                sale_item = SaleItem.objects.create(
                    sale=sale,
                    product=product,
                    quantity=qty,
                    unit_price=unit_price,
                )

                deduct_stock_fifo(
                    product=product,
                    quantity=qty,
                    user=actor_user,
                    sale=sale,
                    store=store.id,
                )

                subtotal += _money(sale_item.total_price)

        except InsufficientStockError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except serializers.ValidationError as exc:
            return Response(
                {"detail": exc.detail if hasattr(exc, "detail") else str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        subtotal = _money(subtotal)
        tax = _money(getattr(sale, "tax_amount", None))
        discount = _money(getattr(sale, "discount_amount", None))
        total = _money(subtotal + tax - discount)

        sale.subtotal_amount = subtotal
        sale.total_amount = total
        sale.status = Sale.STATUS_COMPLETED

        if hasattr(sale, "completed_at") and not getattr(sale, "completed_at", None):
            sale.completed_at = timezone.now()

        sale.save(
            update_fields=["subtotal_amount", "total_amount", "status", "completed_at"]
        )

        if normalized_allocs:
            alloc_total = _money(
                sum((a["amount"] for a in normalized_allocs), Decimal("0.00"))
            )
            if alloc_total != total:
                return Response(
                    {
                        "detail": f"Split payment mismatch: allocations sum({alloc_total}) != sale total({total})."
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if sale.payment_method != "split":
                sale.payment_method = "split"
                sale.save(update_fields=["payment_method"])

            for a in normalized_allocs:
                SalePaymentAllocation.objects.create(
                    sale=sale,
                    method=a["method"],
                    amount=a["amount"],
                    reference=a["reference"],
                    note=a["note"],
                )

        try:
            post_sale_to_ledger(sale=sale)
        except (
            JournalEntryCreationError,
            IdempotencyError,
            AccountResolutionError,
        ) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            return Response(
                {"detail": f"Ledger posting failed: {exc}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(SaleSerializer(sale).data, status=status.HTTP_201_CREATED)


class PublicReceiptView(APIView):
    permission_classes = [AllowAny]
    parser_classes = [JSONParser]

    @extend_schema(
        responses={200: OpenApiResponse(description="Public receipt payload")},
        tags=["Public"],
    )
    def get(self, request, sale_id):
        sale = get_object_or_404(Sale, id=sale_id)
        items = SaleItem.objects.filter(sale=sale).select_related("product")
        return Response(
            {
                "sale": SaleSerializer(sale).data,
                "items": PublicReceiptItemSerializer(items, many=True).data,
            },
            status=status.HTTP_200_OK,
        )
