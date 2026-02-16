# pos/views/api.py

"""
POS API VIEWS (PHASE 1)

Purpose:
- Store-scoped active cart lifecycle
- Add/update/remove/clear items (server-owned pricing)
- Checkout endpoint that finalizes cart into Sale via checkout orchestrator

Hard rules:
- Store context is required for POS cart operations.
- Money is server-owned: unit_price is snapshotted from Product on add (and can be refreshed safely).
"""

from __future__ import annotations

from django.shortcuts import get_object_or_404
from django.db import transaction

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from rest_framework import serializers

from drf_spectacular.utils import extend_schema, OpenApiExample

from pos.models import Cart, CartItem
from pos.serializers import CartSerializer
from products.models import Product
from store.models import Store

from sales.services.checkout_orchestrator import (
    checkout_cart,
    EmptyCartError,
    StockValidationError,
    AccountingPostingError,
    CheckoutError,
)


# =====================================================
# SWAGGER INPUT SERIALIZERS
# =====================================================

class AddCartItemInputSerializer(serializers.Serializer):
    store_id = serializers.UUIDField(required=False, allow_null=True)
    product_id = serializers.UUIDField()
    quantity = serializers.IntegerField(min_value=1)


class UpdateCartItemInputSerializer(serializers.Serializer):
    store_id = serializers.UUIDField(required=False, allow_null=True)
    quantity = serializers.IntegerField(min_value=1)


class ActiveCartQuerySerializer(serializers.Serializer):
    """
    For Swagger docs (GET query params).
    """
    store_id = serializers.UUIDField(required=False, allow_null=True)


class PaymentAllocationInputSerializer(serializers.Serializer):
    """
    Split payment allocation line.
    NOTE: amount must be a POSITIVE decimal string/number (e.g. "1500.00")
    """
    method = serializers.ChoiceField(choices=["cash", "bank", "pos", "transfer", "credit"])
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=0.01)
    reference = serializers.CharField(required=False, allow_blank=True, default="")
    note = serializers.CharField(required=False, allow_blank=True, default="")


class CheckoutCartInputSerializer(serializers.Serializer):
    store_id = serializers.UUIDField(required=False, allow_null=True)

    # payment_method is optional because backend can infer "split" when allocations are provided
    payment_method = serializers.ChoiceField(
        choices=["cash", "bank", "pos", "transfer", "credit", "split"],
        required=False,
        allow_blank=True,
        default="cash",
    )

    # Optional: if present, backend enforces sum(amount) == sale.total_amount and sets method="split"
    payment_allocations = PaymentAllocationInputSerializer(many=True, required=False)


# =====================================================
# API ERROR NORMALIZATION
# =====================================================

def error_response(*, code: str, message: str, http_status: int):
    return Response(
        {"error": {"code": code, "message": message}},
        status=http_status,
    )


# =====================================================
# HELPERS
# =====================================================

def _resolve_store_from_request(*, request) -> Store:
    """
    Resolve the store context for POS actions.

    Priority:
    1) request.query_params.store_id (ActiveCart GET)
    2) request.data.store_id (Add/Update/Checkout)
    3) request.user.store_id (optional future if you add it to user)
    """
    raw = (request.query_params.get("store_id") or "").strip()
    if not raw:
        raw = str((request.data.get("store_id") if isinstance(request.data, dict) else "") or "").strip()

    if not raw:
        user_store_id = getattr(request.user, "store_id", None)
        if user_store_id:
            return get_object_or_404(Store, id=user_store_id, is_active=True)

    if not raw:
        raise serializers.ValidationError(
            {"store_id": "store_id is required for POS cart operations (multi-store scope)."}
        )

    return get_object_or_404(Store, id=raw, is_active=True)


def _get_active_cart_for_store(*, user, store: Store) -> Cart:
    """
    Canonical active cart resolver: exactly one active cart per user per store.
    """
    cart, _ = Cart.objects.get_or_create(
        user=user,
        store=store,
        is_active=True,
    )
    return cart


# =====================================================
# POS API VIEWS
# =====================================================

class POSHealthCheckView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = None

    @extend_schema(
        responses={200: dict},
        description="POS module health check",
    )
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
    """
    Retrieve or create the authenticated user's active cart (STORE-SCOPED).
    """

    permission_classes = [IsAuthenticated]
    serializer_class = CartSerializer

    @extend_schema(
        parameters=[ActiveCartQuerySerializer],
        responses={200: CartSerializer},
        description="Get or create the active cart for the authenticated user (requires store_id)",
    )
    def get(self, request):
        store = _resolve_store_from_request(request=request)
        cart = _get_active_cart_for_store(user=request.user, store=store)
        return Response(CartSerializer(cart).data, status=status.HTTP_200_OK)


class AddCartItemView(APIView):
    """
    Add a product to the active cart (STORE-SCOPED).

    Money rule:
    - Unit price is OWNED by Product and snapshotted server-side.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = CartSerializer

    @extend_schema(
        request=AddCartItemInputSerializer,
        responses={200: CartSerializer},
        description="Add a product to the active cart (requires store_id; increments quantity if exists)",
    )
    @transaction.atomic
    def post(self, request):
        serializer = AddCartItemInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        store = _resolve_store_from_request(request=request)

        product_id = serializer.validated_data["product_id"]
        quantity = int(serializer.validated_data["quantity"])

        product = get_object_or_404(Product, id=product_id, is_active=True)

        if getattr(product, "store_id", None) and product.store_id != store.id:
            return error_response(
                code="STORE_MISMATCH",
                message="Product belongs to a different store.",
                http_status=status.HTTP_400_BAD_REQUEST,
            )

        cart = _get_active_cart_for_store(user=request.user, store=store)

        cart_item, created = CartItem.objects.get_or_create(
            cart=cart,
            product=product,
            defaults={
                "quantity": quantity,
                "unit_price": product.unit_price,  # snapshot
            },
        )

        if not created:
            cart_item.quantity = int(cart_item.quantity or 0) + quantity

            # Optional but recommended: refresh snapshot to current product price when item is re-added
            cart_item.unit_price = product.unit_price
            cart_item.save(update_fields=["quantity", "unit_price"])

        return Response(CartSerializer(cart).data, status=status.HTTP_200_OK)


class UpdateCartItemView(APIView):
    """
    Update quantity of a cart item (STORE-SCOPED).

    Rules:
    - Requires store context (prevents cross-store confusion)
    - Only items in the active cart for that store can be modified
    - Quantity must be >= 1
    """

    permission_classes = [IsAuthenticated]
    serializer_class = CartSerializer

    @extend_schema(
        request=UpdateCartItemInputSerializer,
        responses={200: CartSerializer},
        description="Update quantity of a cart item (requires store_id)",
    )
    @transaction.atomic
    def patch(self, request, item_id):
        serializer = UpdateCartItemInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        store = _resolve_store_from_request(request=request)
        quantity = int(serializer.validated_data["quantity"])

        cart = _get_active_cart_for_store(user=request.user, store=store)

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
    """
    Remove an item from the active cart (STORE-SCOPED).
    """

    permission_classes = [IsAuthenticated]
    serializer_class = CartSerializer

    @extend_schema(
        parameters=[ActiveCartQuerySerializer],
        responses={200: CartSerializer},
        description="Remove an item from the active cart (requires store_id)",
    )
    @transaction.atomic
    def delete(self, request, item_id):
        store = _resolve_store_from_request(request=request)
        cart = _get_active_cart_for_store(user=request.user, store=store)

        cart_item = get_object_or_404(
            CartItem,
            id=item_id,
            cart=cart,
            cart__is_active=True,
        )

        cart_item.delete()

        return Response(CartSerializer(cart).data, status=status.HTTP_200_OK)


class ClearCartView(APIView):
    """
    Clear the active cart (STORE-SCOPED).

    This is a POS UX must-have: cashier cancels a cart in one click.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = CartSerializer

    @extend_schema(
        parameters=[ActiveCartQuerySerializer],
        responses={200: CartSerializer},
        description="Clear active cart items (requires store_id)",
    )
    @transaction.atomic
    def delete(self, request):
        store = _resolve_store_from_request(request=request)
        cart = _get_active_cart_for_store(user=request.user, store=store)

        cart.items.all().delete()
        cart.refresh_from_db()

        return Response(CartSerializer(cart).data, status=status.HTTP_200_OK)


class CheckoutCartView(APIView):
    """
    Checkout the active cart and create a completed Sale (STORE-SCOPED).

    Calls:
    - sales.services.checkout_orchestrator.checkout_cart()
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=CheckoutCartInputSerializer,
        responses={200: dict},
        description="Checkout active cart into a completed sale (requires store_id).",
        examples=[
            OpenApiExample(
                "Single payment (cash)",
                summary="Single payment",
                value={
                    "store_id": "07d0722f-92fd-4a83-b84e-6e25f034a647",
                    "payment_method": "cash",
                },
                request_only=True,
            ),
            OpenApiExample(
                "Split payment (Example B: cash + pos + credit)",
                summary="Split payment (multi-leg)",
                value={
                    "store_id": "07d0722f-92fd-4a83-b84e-6e25f034a647",
                    "payment_method": "split",
                    "payment_allocations": [
                        {"method": "cash", "amount": "2000.00", "reference": "", "note": ""},
                        {"method": "pos", "amount": "1500.00", "reference": "POS-8891", "note": ""},
                        {"method": "credit", "amount": "2250.00", "reference": "", "note": "Customer owes balance"},
                    ],
                },
                request_only=True,
            ),
        ],
    )
    @transaction.atomic
    def post(self, request):
        serializer = CheckoutCartInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        store = _resolve_store_from_request(request=request)
        cart = _get_active_cart_for_store(user=request.user, store=store)

        payment_method = (serializer.validated_data.get("payment_method") or "").strip() or "cash"
        payment_allocations = serializer.validated_data.get("payment_allocations") or None

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

        return Response(
            {
                "sale_id": str(sale.id),
                "sale_status": sale.status,
                "total_amount": str(sale.total_amount),
                "payment_method": sale.payment_method,
                "completed_at": sale.completed_at.isoformat() if sale.completed_at else None,
            },
            status=status.HTTP_200_OK,
        )
