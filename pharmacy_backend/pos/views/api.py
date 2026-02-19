"""
PATH: pos/views/api.py

POS API VIEWS (PHASE 1)

Backward compatibility strategy:
- If store_id is provided -> store-scoped cart behavior.
- If store_id is NOT provided -> legacy single-store cart behavior (store=NULL).

This is required because existing tests and early deployments may not pass store_id.
"""

from __future__ import annotations

from django.db import transaction
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiExample, extend_schema
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from pos.models import Cart, CartItem
from pos.serializers import CartSerializer
from products.models import Product
from sales.services.checkout_orchestrator import (
    AccountingPostingError,
    CheckoutError,
    EmptyCartError,
    StockValidationError,
    checkout_cart,
)
from store.models import Store


class AddCartItemInputSerializer(serializers.Serializer):
    store_id = serializers.UUIDField(required=False, allow_null=True)
    product_id = serializers.UUIDField()
    quantity = serializers.IntegerField(min_value=1)


class UpdateCartItemInputSerializer(serializers.Serializer):
    store_id = serializers.UUIDField(required=False, allow_null=True)
    quantity = serializers.IntegerField(min_value=1)


class ActiveCartQuerySerializer(serializers.Serializer):
    store_id = serializers.UUIDField(required=False, allow_null=True)


class PaymentAllocationInputSerializer(serializers.Serializer):
    method = serializers.ChoiceField(
        choices=["cash", "bank", "pos", "transfer", "credit"]
    )
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=0.01)
    reference = serializers.CharField(required=False, allow_blank=True, default="")
    note = serializers.CharField(required=False, allow_blank=True, default="")


class CheckoutCartInputSerializer(serializers.Serializer):
    store_id = serializers.UUIDField(required=False, allow_null=True)
    payment_method = serializers.ChoiceField(
        choices=["cash", "bank", "pos", "transfer", "credit", "split"],
        required=False,
        allow_blank=True,
        default="cash",
    )
    payment_allocations = PaymentAllocationInputSerializer(many=True, required=False)


def error_response(*, code: str, message: str, http_status: int):
    return Response({"error": {"code": code, "message": message}}, status=http_status)


def _raw_store_id_from_request(*, request) -> str:
    raw = (request.query_params.get("store_id") or "").strip()
    if not raw:
        raw = str(
            (request.data.get("store_id") if isinstance(request.data, dict) else "")
            or ""
        ).strip()
    return raw


def _resolve_store_optional(*, request) -> Store | None:
    """
    Returns Store if store_id is present; otherwise None (legacy mode).
    """
    raw = _raw_store_id_from_request(request=request)
    if not raw:
        return None
    return get_object_or_404(Store, id=raw, is_active=True)


def _get_active_cart(*, user, store: Store | None) -> Cart:
    """
    Backward compatible:
    - store provided: per-user-per-store active cart
    - store None: legacy active cart (store=NULL)
    """
    cart, _ = Cart.objects.get_or_create(
        user=user,
        store=store,
        is_active=True,
    )
    return cart


class POSHealthCheckView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = None

    @extend_schema(responses={200: dict}, description="POS module health check")
    def get(self, request):
        return Response(
            {
                "status": "ok",
                "module": "pos",
                "user": request.user.email,
                "role": request.user.role,
            }
        )


class ActiveCartView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = CartSerializer

    @extend_schema(
        parameters=[ActiveCartQuerySerializer],
        responses={200: CartSerializer},
        description="Get or create the active cart for the authenticated user (store_id optional for legacy mode)",
    )
    def get(self, request):
        store = _resolve_store_optional(request=request)
        cart = _get_active_cart(user=request.user, store=store)
        return Response(CartSerializer(cart).data, status=status.HTTP_200_OK)


class AddCartItemView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = CartSerializer

    @extend_schema(
        request=AddCartItemInputSerializer,
        responses={200: CartSerializer},
        description="Add a product to the active cart (store_id optional for legacy mode)",
    )
    @transaction.atomic
    def post(self, request):
        serializer = AddCartItemInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        store = _resolve_store_optional(request=request)

        product_id = serializer.validated_data["product_id"]
        quantity = int(serializer.validated_data["quantity"])

        product = get_object_or_404(Product, id=product_id, is_active=True)

        # If store context is provided, enforce store match.
        if store is not None and getattr(product, "store_id", None):
            if product.store_id != store.id:
                return error_response(
                    code="STORE_MISMATCH",
                    message="Product belongs to a different store.",
                    http_status=status.HTTP_400_BAD_REQUEST,
                )

        cart = _get_active_cart(user=request.user, store=store)

        cart_item, created = CartItem.objects.get_or_create(
            cart=cart,
            product=product,
            defaults={
                "quantity": quantity,
                "unit_price": product.unit_price,
            },
        )

        if not created:
            cart_item.quantity = int(cart_item.quantity or 0) + quantity
            cart_item.unit_price = product.unit_price
            cart_item.save(update_fields=["quantity", "unit_price"])

        return Response(CartSerializer(cart).data, status=status.HTTP_200_OK)


class UpdateCartItemView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = CartSerializer

    @extend_schema(
        request=UpdateCartItemInputSerializer,
        responses={200: CartSerializer},
        description="Update quantity of a cart item (store_id optional for legacy mode)",
    )
    @transaction.atomic
    def patch(self, request, item_id):
        serializer = UpdateCartItemInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        store = _resolve_store_optional(request=request)
        quantity = int(serializer.validated_data["quantity"])

        cart = _get_active_cart(user=request.user, store=store)

        cart_item = get_object_or_404(
            CartItem,
            id=item_id,
            cart=cart,
            cart__is_active=True,
        )

        cart_item.quantity = quantity
        cart_item.save(update_fields=["quantity"])

        return Response(CartSerializer(cart).data, status=status.HTTP_200_OK)


class RemoveCartItemView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = CartSerializer

    @extend_schema(
        parameters=[ActiveCartQuerySerializer],
        responses={200: CartSerializer},
        description="Remove an item from the active cart (store_id optional for legacy mode)",
    )
    @transaction.atomic
    def delete(self, request, item_id):
        store = _resolve_store_optional(request=request)
        cart = _get_active_cart(user=request.user, store=store)

        cart_item = get_object_or_404(
            CartItem,
            id=item_id,
            cart=cart,
            cart__is_active=True,
        )
        cart_item.delete()

        return Response(CartSerializer(cart).data, status=status.HTTP_200_OK)


class ClearCartView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = CartSerializer

    @extend_schema(
        parameters=[ActiveCartQuerySerializer],
        responses={200: CartSerializer},
        description="Clear active cart items (store_id optional for legacy mode)",
    )
    @transaction.atomic
    def delete(self, request):
        store = _resolve_store_optional(request=request)
        cart = _get_active_cart(user=request.user, store=store)

        cart.items.all().delete()
        cart.refresh_from_db()

        return Response(CartSerializer(cart).data, status=status.HTTP_200_OK)


class CheckoutCartView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=CheckoutCartInputSerializer,
        responses={201: dict},
        description="Checkout active cart into a completed sale (store_id optional for legacy mode).",
        examples=[
            OpenApiExample(
                "Single payment (cash)",
                summary="Single payment",
                value={"payment_method": "cash"},
                request_only=True,
            ),
        ],
    )
    @transaction.atomic
    def post(self, request):
        serializer = CheckoutCartInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        store = _resolve_store_optional(request=request)
        cart = _get_active_cart(user=request.user, store=store)

        payment_method = (
            serializer.validated_data.get("payment_method") or ""
        ).strip() or "cash"
        payment_allocations = (
            serializer.validated_data.get("payment_allocations") or None
        )

        try:
            sale = checkout_cart(
                user=request.user,
                cart=cart,
                payment_method=payment_method,
                payment_allocations=payment_allocations,
            )
        except EmptyCartError as exc:
            return error_response(
                code="EMPTY_CART",
                message=str(exc),
                http_status=status.HTTP_400_BAD_REQUEST,
            )
        except StockValidationError as exc:
            return error_response(
                code="INSUFFICIENT_STOCK",
                message=str(exc),
                http_status=status.HTTP_400_BAD_REQUEST,
            )
        except AccountingPostingError as exc:
            return error_response(
                code="ACCOUNTING_POST_FAILED",
                message=str(exc),
                http_status=status.HTTP_400_BAD_REQUEST,
            )
        except CheckoutError as exc:
            return error_response(
                code="CHECKOUT_FAILED",
                message=str(exc),
                http_status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as exc:
            return error_response(
                code="UNKNOWN_ERROR",
                message=f"Checkout failed: {exc}",
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # IMPORTANT: tests expect 201
        return Response(
            {
                "sale_id": str(sale.id),
                "sale_status": sale.status,
                "total_amount": str(sale.total_amount),
                "payment_method": sale.payment_method,
                "completed_at": sale.completed_at.isoformat()
                if sale.completed_at
                else None,
            },
            status=status.HTTP_201_CREATED,
        )
