# public/views/order.py
from __future__ import annotations

import uuid
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.parsers import JSONParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from products.models import Product, StockBatch
from public.serializers import (
    PublicOrderInitiateResponseSerializer,
    PublicOrderInitiateSerializer,
    PublicOrderStatusResponseSerializer,
)
from public.services.paystack import paystack_initialize_transaction
from sales.models import OnlineOrder, OnlineOrderItem, PaymentAttempt
from store.models import Store

TWOPLACES = Decimal("0.01")


class PublicWriteThrottle(AnonRateThrottle):
    """
    For public write endpoints (initiate checkout, legacy checkout).
    Uses REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']['public_write'].
    """

    scope = "public_write"


class PublicPollThrottle(AnonRateThrottle):
    """
    For public polling endpoints (order status).
    Uses REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']['public_poll'].
    """

    scope = "public_poll"


def _money(v) -> Decimal:
    if v is None or v == "":
        return Decimal("0.00")
    return Decimal(str(v)).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def _model_fields(model_cls) -> set[str]:
    try:
        return {f.name for f in model_cls._meta.get_fields()}
    except Exception:
        return set()


def _safe_create(model_cls, **kwargs):
    allowed = _model_fields(model_cls)
    cleaned = {k: v for k, v in kwargs.items() if k in allowed}
    return model_cls.objects.create(**cleaned)


def _safe_set(obj, **kwargs):
    allowed = _model_fields(obj.__class__)
    touched = []
    for k, v in kwargs.items():
        if k in allowed:
            setattr(obj, k, v)
            touched.append(k)
    return touched


def _available_stock_for_product(*, product, store: Store) -> int:
    today = timezone.localdate()

    base = StockBatch.objects.filter(
        product=product,
        is_active=True,
        expiry_date__gte=today,
        quantity_remaining__gt=0,
    )

    store_qs = base.filter(store_id=store.id)
    if store_qs.exists():
        qs = store_qs
    else:
        qs = base.filter(store__isnull=True)

    return sum(int(b.quantity_remaining or 0) for b in qs)


def _paystack_callback_url() -> str:
    direct = getattr(settings, "PAYSTACK_CALLBACK_URL", "") or ""
    if direct:
        return str(direct)

    payments = getattr(settings, "PAYMENTS", {}) or {}
    ps = (payments.get("PAYSTACK") or {}) if isinstance(payments, dict) else {}
    return str(ps.get("CALLBACK_URL") or "")


class PublicOrderInitiateView(APIView):
    permission_classes = [AllowAny]
    parser_classes = [JSONParser]
    throttle_classes = [PublicWriteThrottle]

    @extend_schema(
        tags=["Public"],
        request=PublicOrderInitiateSerializer,
        responses={
            201: PublicOrderInitiateResponseSerializer,
            400: OpenApiResponse(description="Validation error"),
            404: OpenApiResponse(description="Store not found"),
            409: OpenApiResponse(description="Insufficient stock"),
            429: OpenApiResponse(description="Rate limited"),
            502: OpenApiResponse(description="Payment provider error"),
        },
        description="Phase 4 safe checkout: create OnlineOrder (pending payment) + init Paystack.",
    )
    @transaction.atomic
    def post(self, request, *args, **kwargs):
        s = PublicOrderInitiateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        data = s.validated_data

        store = get_object_or_404(Store, id=data["store_id"], is_active=True)

        items = data.get("items") or []
        if not items:
            return Response(
                {"detail": "Cart is empty"}, status=status.HTTP_400_BAD_REQUEST
            )

        order = _safe_create(
            OnlineOrder,
            store=store,
            customer_name=str(data.get("customer_name") or "").strip(),
            customer_phone=str(data.get("customer_phone") or "").strip(),
            customer_email=str(data.get("customer_email") or "").strip(),
            status=getattr(OnlineOrder, "STATUS_PENDING_PAYMENT", "pending_payment"),
            subtotal_amount=Decimal("0.00"),
            tax_amount=Decimal("0.00"),
            discount_amount=Decimal("0.00"),
            total_amount=Decimal("0.00"),
        )

        subtotal = Decimal("0.00")

        for line in items:
            product = get_object_or_404(Product, id=line["product_id"], is_active=True)

            p_store_id = getattr(product, "store_id", None)
            if p_store_id and str(p_store_id) != str(store.id):
                return Response(
                    {"detail": "Product belongs to a different store."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            qty = int(line["quantity"])
            if qty <= 0:
                return Response(
                    {"detail": "quantity must be >= 1"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            available = _available_stock_for_product(product=product, store=store)
            if available < qty:
                return Response(
                    {
                        "detail": (
                            f"Insufficient stock for {getattr(product, 'name', 'product')}. "
                            f"Requested: {qty}, Available: {available}"
                        )
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            unit_price = _money(getattr(product, "unit_price", None))
            total_price = _money(unit_price * Decimal(qty))

            _safe_create(
                OnlineOrderItem,
                order=order,
                product=product,
                quantity=qty,
                unit_price=unit_price,
                total_price=total_price,
            )

            subtotal += total_price

        subtotal = _money(subtotal)
        total = subtotal  # hooks for tax/discount later

        touched = _safe_set(order, subtotal_amount=subtotal, total_amount=total)
        if touched:
            order.save(update_fields=touched)

        email = (getattr(order, "customer_email", "") or "").strip()
        if not email:
            email = f"guest_{uuid.uuid4().hex[:10]}@example.com"

        reference = f"ORD-{order.id}-{uuid.uuid4().hex[:8]}".upper()

        attempt = _safe_create(
            PaymentAttempt,
            order=order,
            provider=getattr(PaymentAttempt, "PROVIDER_PAYSTACK", "paystack"),
            reference=reference,
            amount=total,
            currency="NGN",
            status=getattr(PaymentAttempt, "STATUS_INITIATED", "initiated"),
        )

        callback_url = _paystack_callback_url()

        try:
            init = paystack_initialize_transaction(
                email=email,
                amount_naira=total,
                reference=reference,
                callback_url=callback_url,
                metadata={
                    "order_id": str(order.id),
                    "order_no": getattr(order, "order_no", ""),
                    "store_id": str(store.id),
                },
            )
        except Exception as exc:
            touched = _safe_set(
                attempt,
                status=getattr(PaymentAttempt, "STATUS_FAILED", "failed"),
                provider_payload={"error": str(exc)},
            )
            if touched:
                attempt.save(update_fields=touched)
            return Response(
                {"detail": f"Payment provider init failed: {exc}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        authorization_url = str(init.get("authorization_url") or "").strip()

        touched = _safe_set(
            attempt,
            authorization_url=authorization_url,
            status=getattr(PaymentAttempt, "STATUS_REDIRECTED", "redirected"),
            provider_payload=init,
        )
        if touched:
            attempt.save(update_fields=touched)

        return Response(
            {
                "order_id": order.id,
                "order_no": getattr(order, "order_no", ""),
                "amount": getattr(order, "total_amount", total),
                "currency": getattr(attempt, "currency", "NGN"),
                "provider": getattr(attempt, "provider", "paystack"),
                "reference": getattr(attempt, "reference", reference),
                "authorization_url": authorization_url,
            },
            status=status.HTTP_201_CREATED,
        )


class PublicOrderStatusView(APIView):
    permission_classes = [AllowAny]
    parser_classes = [JSONParser]
    throttle_classes = [PublicPollThrottle]

    @extend_schema(
        tags=["Public"],
        responses={
            200: PublicOrderStatusResponseSerializer,
            429: OpenApiResponse(description="Rate limited"),
        },
    )
    def get(self, request, order_id, *args, **kwargs):
        order = get_object_or_404(OnlineOrder, id=order_id)

        sale_id = None
        if getattr(order, "sale_id", None):
            sale_id = getattr(getattr(order, "sale", None), "id", None) or order.sale_id

        return Response(
            {
                "order_id": order.id,
                "order_no": getattr(order, "order_no", ""),
                "status": getattr(order, "status", None),
                "amount": getattr(order, "total_amount", None),
                "currency": "NGN",
                "paid_at": getattr(order, "paid_at", None),
                "sale_id": sale_id,
            },
            status=status.HTTP_200_OK,
        )
