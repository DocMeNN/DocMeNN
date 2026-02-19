# pos/views.py

from __future__ import annotations

from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import generics, serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from permissions.roles import (
    IsCashier,
    IsPharmacist,
    IsReception,
    IsStaff,
)
from pos.models import Cart, CartItem
from pos.serializers import CartSerializer  # ✅ use your current CartSerializer
from products.models import Product
from sales.serializers import SaleSerializer
from sales.services.checkout_orchestrator import (
    AccountingPostingError,
    EmptyCartError,
    StockValidationError,
    checkout_cart,
)
from store.models import Store

# ============================================================
# INPUT SERIALIZERS (for validation)
# ============================================================


class AddToCartInputSerializer(serializers.Serializer):
    store_id = serializers.UUIDField()
    product_id = serializers.UUIDField()
    quantity = serializers.IntegerField(min_value=1)


class CheckoutInputSerializer(serializers.Serializer):
    store_id = serializers.UUIDField()
    payment_method = serializers.CharField(
        required=False, allow_blank=True, allow_null=True
    )


# ============================================================
# HELPERS
# ============================================================


def _resolve_store(*, store_id):
    return get_object_or_404(Store, id=store_id, is_active=True)


def get_cart(*, user, store: Store) -> Cart:
    """
    Store-scoped cart:
    - One active cart per user per store
    """
    cart, _ = Cart.objects.get_or_create(
        user=user,
        store=store,
        is_active=True,
    )
    return cart


def _assert_product_belongs_to_store(*, product: Product, store: Store):
    """
    If Product has store_id, enforce that it matches cart store.
    (If product.store is null, we allow it as shared catalog.)
    """
    product_store_id = getattr(product, "store_id", None)
    if product_store_id and product_store_id != store.id:
        raise serializers.ValidationError("Product belongs to a different store.")


# ============================================================
# VIEW CART
# ============================================================


class POSCartView(generics.GenericAPIView):
    """
    GET active POS cart (store-scoped)

    Query param:
      ?store_id=<uuid>
    """

    serializer_class = CartSerializer
    permission_classes = [IsAuthenticated, IsPharmacist | IsCashier | IsReception]

    def get(self, request, *args, **kwargs):
        raw_store_id = (request.query_params.get("store_id") or "").strip()
        if not raw_store_id:
            return Response(
                {"detail": "store_id is required as a query param."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        store = _resolve_store(store_id=raw_store_id)
        cart = get_cart(user=request.user, store=store)
        return Response(CartSerializer(cart).data, status=status.HTTP_200_OK)


# ============================================================
# ADD TO CART
# ============================================================


class AddToCartView(generics.GenericAPIView):
    """
    Add product to POS cart (store-scoped)

    Body:
      {
        "store_id": "...",
        "product_id": "...",
        "quantity": 1
      }

    RULES:
    - No stock deduction here
    - Unit price snapshot comes from Product.unit_price
    """

    serializer_class = AddToCartInputSerializer
    permission_classes = [IsAuthenticated, IsStaff]

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        s = self.get_serializer(data=request.data)
        s.is_valid(raise_exception=True)
        data = s.validated_data

        store = _resolve_store(store_id=data["store_id"])
        cart = get_cart(user=request.user, store=store)

        product = get_object_or_404(Product, id=data["product_id"], is_active=True)
        _assert_product_belongs_to_store(product=product, store=store)

        qty = int(data["quantity"])

        # Create or increment
        item, created = CartItem.objects.get_or_create(
            cart=cart,
            product=product,
            defaults={
                "quantity": qty,
                "unit_price": product.unit_price,  # ✅ snapshot
            },
        )

        if not created:
            item.quantity = int(item.quantity or 0) + qty
            item.save(update_fields=["quantity"])

        cart.refresh_from_db()
        return Response(CartSerializer(cart).data, status=status.HTTP_200_OK)


# ============================================================
# REMOVE FROM CART
# ============================================================


class RemoveFromCartView(generics.DestroyAPIView):
    """
    Remove item from active POS cart (store-scoped)

    URL:
      DELETE /pos/cart/items/<pk>/
    """

    permission_classes = [IsAuthenticated, IsStaff]

    def delete(self, request, pk, *args, **kwargs):
        # Ensure the item belongs to the requesting user's ACTIVE cart
        item = get_object_or_404(
            CartItem,
            id=pk,
            cart__user=request.user,
            cart__is_active=True,
        )

        cart = item.cart
        item.delete()

        cart.refresh_from_db()
        return Response(CartSerializer(cart).data, status=status.HTTP_200_OK)


# ============================================================
# CHECKOUT
# ============================================================


class CheckoutView(generics.GenericAPIView):
    """
    Checkout POS cart (store-scoped, orchestrator-driven)

    Body:
      {
        "store_id": "...",
        "payment_method": "cash" | "bank" | "card" | "transfer" | "credit"
      }

    GUARANTEES:
    - Atomic
    - FIFO batch deduction
    - Accounting ledger posting
    - Cart deactivation
    """

    serializer_class = CheckoutInputSerializer
    permission_classes = [IsAuthenticated, IsPharmacist | IsCashier]

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        s = self.get_serializer(data=request.data)
        s.is_valid(raise_exception=True)
        data = s.validated_data

        store = _resolve_store(store_id=data["store_id"])
        cart = get_cart(user=request.user, store=store)

        try:
            sale = checkout_cart(
                user=request.user,
                cart=cart,
                payment_method=data.get("payment_method"),
            )
        except EmptyCartError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except StockValidationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except AccountingPostingError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        # Return full sale payload (or keep your minimal response if you prefer)
        return Response(
            {
                "message": "Checkout successful",
                "sale": SaleSerializer(sale).data,
            },
            status=status.HTTP_201_CREATED,
        )
