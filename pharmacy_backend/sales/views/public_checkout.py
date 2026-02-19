# sales/views/public_checkout.py

"""
PUBLIC CHECKOUT (ONLINE STORE)

Goal:
- Allow anonymous customers to checkout a store-scoped cart payload
- Use the SAME backend truth rules as POS:
  - Validate stock per store (FIFO/FEFO engine)
  - Deduct stock via canonical FIFO service (writes StockMovement)
  - Create immutable Sale + SaleItems
  - Post to accounting ledger

IMPORTANT:
- We do NOT create POS Cart rows for public users.
  POS Cart is staff-only and requires a user + active store cart.
- Public cart remains client-side (localStorage) in V1.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from accounting.services.exceptions import (
    AccountResolutionError,
    IdempotencyError,
    JournalEntryCreationError,
)
from accounting.services.posting import post_sale_to_ledger
from products.models import Product
from products.services.stock_fifo import InsufficientStockError, deduct_stock_fifo
from sales.models import Sale, SaleItem
from sales.serializers.sale import SaleSerializer
from store.models import Store

TWOPLACES = Decimal("0.01")


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


# -----------------------------
# Input serializers
# -----------------------------


class PublicCartItemSerializer(serializers.Serializer):
    product_id = serializers.UUIDField()
    quantity = serializers.IntegerField(min_value=1)


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


class PublicCheckoutView(APIView):
    """
    POST /api/public/checkout/

    Body:
    {
      "store_id": "...",
      "customer_name": "Jane Doe",
      "customer_phone": "080...",
      "customer_email": "jane@example.com",
      "payment_method": "online",
      "items": [
        {"product_id": "...", "quantity": 2},
        ...
      ]
    }

    Returns:
    - Sale payload (serializer) + sale_id convenience field
    """

    permission_classes = [AllowAny]

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

        payment_method = _normalize_payment_method(data.get("payment_method"))

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
            raise serializers.ValidationError(str(exc)) from exc

        subtotal = _money(subtotal)
        tax = _money(getattr(sale, "tax_amount", None))
        discount = _money(getattr(sale, "discount_amount", None))
        total = _money(subtotal + tax - discount)

        sale.subtotal_amount = subtotal
        sale.total_amount = total
        sale.status = Sale.STATUS_COMPLETED
        sale.save(
            update_fields=["subtotal_amount", "total_amount", "status", "completed_at"]
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

        payload = SaleSerializer(sale).data
        payload["sale_id"] = str(sale.id)
        return Response(payload, status=status.HTTP_201_CREATED)
