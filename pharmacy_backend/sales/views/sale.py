# sales/views/sale.py

from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from pos.models import Cart
from sales.serializers import SaleSerializer
from sales.services.checkout_orchestrator import (
    CheckoutError,
    EmptyCartError,
    StockValidationError,
    checkout_cart,
)
from store.models import Store


class PaymentAllocationInputSerializer(serializers.Serializer):
    method = serializers.ChoiceField(
        choices=["cash", "bank", "pos", "transfer", "credit"],
        help_text="One payment leg method",
    )
    amount = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text="Amount for this payment leg",
    )
    reference = serializers.CharField(required=False, allow_blank=True, default="")
    note = serializers.CharField(required=False, allow_blank=True, default="")


class CheckoutInputSerializer(serializers.Serializer):
    """
    Explicit checkout input serializer.

    Documents ONLY what the client is allowed to send.

    MULTI-STORE RULE:
    - store_id is mandatory so we never pick the wrong cart.

    SPLIT PAYMENT RULE:
    - If payment_allocations is provided, backend enforces:
      sum(amount) == computed sale.total_amount
      and sets sale.payment_method="split"
    """

    store_id = serializers.UUIDField(required=True)

    payment_method = serializers.CharField(
        required=False,
        default="cash",
        help_text="Legacy single payment method (cash, bank, pos, transfer, credit). Ignored when payment_allocations is provided.",
    )

    payment_allocations = PaymentAllocationInputSerializer(
        many=True,
        required=False,
        help_text="Optional split payments. Sum must equal sale total.",
    )


class CheckoutSaleView(APIView):
    """
    POS CHECKOUT ENDPOINT (AUTHORITATIVE)

    GUARANTEES:
    - Atomic checkout
    - FIFO stock deduction
    - Immutable Sale & SaleItems
    - Cart is single-use
    - Store-scoped cart selection
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=CheckoutInputSerializer,
        responses={201: SaleSerializer},
        description="Finalize active cart (store-scoped) and create an immutable sale",
    )
    def post(self, request):
        serializer = CheckoutInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        store_id = serializer.validated_data["store_id"]
        payment_method = serializer.validated_data.get("payment_method", "cash")
        payment_allocations = serializer.validated_data.get("payment_allocations", None)

        # Ensure store exists and is active
        try:
            store = Store.objects.get(id=store_id, is_active=True)
        except Store.DoesNotExist:
            return Response(
                {"detail": "Invalid store_id or store is inactive."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            cart = Cart.objects.get(
                user=request.user,
                store=store,
                is_active=True,
            )

            sale = checkout_cart(
                user=request.user,
                cart=cart,
                payment_method=payment_method,
                payment_allocations=payment_allocations,
            )

            return Response(
                SaleSerializer(sale).data,
                status=status.HTTP_201_CREATED,
            )

        except Cart.DoesNotExist:
            return Response(
                {"detail": "No active cart found for this store."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        except EmptyCartError as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        except StockValidationError as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_409_CONFLICT,
            )

        except CheckoutError as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
