# public/views/paystack_webhook.py
from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.db import transaction
from django.utils import timezone

from rest_framework import status
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
from products.services.stock_fifo import InsufficientStockError, deduct_stock_fifo
from public.services.paystack import verify_paystack_signature, verify_paystack_transaction
from sales.models import OnlineOrder, OnlineOrderItem, PaymentAttempt, Sale, SaleItem

TWOPLACES = Decimal("0.01")


class WebhookThrottle(AnonRateThrottle):
    """
    Keep high. We MUST avoid blocking provider retries.
    Uses REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']['webhook'].
    """
    scope = "webhook"


def _money(v) -> Decimal:
    if v is None or v == "":
        return Decimal("0.00")
    try:
        return Decimal(str(v)).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0.00")


def _kobo_to_naira(kobo) -> Decimal:
    try:
        return _money(Decimal(str(int(kobo))) / Decimal("100"))
    except Exception:
        return Decimal("0.00")


def _attempt_status(name: str, fallback: str) -> str:
    return getattr(PaymentAttempt, name, fallback)


def _order_status(name: str, fallback: str) -> str:
    return getattr(OnlineOrder, name, fallback)


def _safe_set_attempt_payload(attempt: PaymentAttempt, payload):
    if hasattr(attempt, "provider_payload"):
        attempt.provider_payload = payload


def _mark_attempt_verified(attempt: PaymentAttempt, payload):
    attempt.status = _attempt_status("STATUS_VERIFIED", "verified")
    if hasattr(attempt, "verified_at"):
        attempt.verified_at = timezone.now()
    _safe_set_attempt_payload(attempt, payload)

    fields = ["status"]
    if hasattr(attempt, "verified_at"):
        fields.append("verified_at")
    if hasattr(attempt, "provider_payload"):
        fields.append("provider_payload")
    attempt.save(update_fields=fields)


def _mark_attempt_failed(attempt: PaymentAttempt, payload, *, reason: str):
    attempt.status = _attempt_status("STATUS_FAILED", "failed")
    _safe_set_attempt_payload(attempt, {"error": reason, "payload": payload})

    fields = ["status"]
    if hasattr(attempt, "provider_payload"):
        fields.append("provider_payload")
    attempt.save(update_fields=fields)


@transaction.atomic
def _finalize_order_to_sale(*, order_id):
    order = OnlineOrder.objects.select_for_update().get(id=order_id)

    if getattr(order, "sale_id", None):
        return order.sale  # idempotent

    sale_kwargs = dict(
        user=None,
        payment_method="online",
        status=Sale.STATUS_DRAFT,
        subtotal_amount=_money(getattr(order, "subtotal_amount", None)),
        tax_amount=_money(getattr(order, "tax_amount", None)),
        discount_amount=_money(getattr(order, "discount_amount", None)),
        total_amount=_money(getattr(order, "total_amount", None)),
    )

    if hasattr(Sale, "store_id"):
        sale_kwargs["store_id"] = getattr(order, "store_id", None)
    elif hasattr(Sale, "store"):
        sale_kwargs["store"] = getattr(order, "store", None)

    sale = Sale.objects.create(**sale_kwargs)

    store_ctx = getattr(order, "store", None) or getattr(order, "store_id", None)

    items = OnlineOrderItem.objects.filter(order=order).select_related("product")
    for it in items:
        product = it.product
        qty = int(getattr(it, "quantity", 0) or 0)
        if qty <= 0:
            continue

        SaleItem.objects.create(
            sale=sale,
            product=product,
            quantity=qty,
            unit_price=_money(getattr(it, "unit_price", None)),
        )

        deduct_stock_fifo(
            product=product,
            quantity=qty,
            user=None,
            sale=sale,
            store=store_ctx,
        )

    sale.status = Sale.STATUS_COMPLETED
    if hasattr(sale, "completed_at") and not getattr(sale, "completed_at", None):
        sale.completed_at = timezone.now()
        sale.save(update_fields=["status", "completed_at"])
    else:
        sale.save(update_fields=["status"])

    post_sale_to_ledger(sale=sale)

    order.sale = sale
    order.save(update_fields=["sale"])

    return sale


class PaystackWebhookView(APIView):
    permission_classes = [AllowAny]
    parser_classes = [JSONParser]
    throttle_classes = [WebhookThrottle]

    def post(self, request, *args, **kwargs):
        raw_body = getattr(request, "body", b"") or b""
        try:
            signature = request.headers.get("x-paystack-signature")
        except Exception:
            signature = None

        if not verify_paystack_signature(raw_body=raw_body, signature=signature):
            # Ack as 400 is OK; Paystack may retry. Signature failures should not pass.
            return Response({"ok": False, "detail": "Invalid signature"}, status=status.HTTP_400_BAD_REQUEST)

        payload = request.data or {}
        data = payload.get("data") or {}

        reference = str(data.get("reference") or "").strip()
        if not reference:
            return Response({"ok": True, "detail": "No reference"}, status=status.HTTP_200_OK)

        try:
            with transaction.atomic():
                attempt = (
                    PaymentAttempt.objects.select_for_update()
                    .filter(reference=reference)
                    .select_related("order")
                    .first()
                )
                if not attempt:
                    return Response({"ok": True, "detail": "Unknown reference"}, status=status.HTTP_200_OK)

                if getattr(attempt, "status", "") == _attempt_status("STATUS_VERIFIED", "verified"):
                    return Response({"ok": True, "detail": "Already verified"}, status=status.HTTP_200_OK)

                verify = verify_paystack_transaction(reference=reference)
                if (not verify.get("ok")) or (str(verify.get("status") or "").lower() != "success"):
                    _mark_attempt_failed(attempt, payload, reason="Verify API: not successful")
                    return Response({"ok": True, "detail": "Verify not successful"}, status=status.HTTP_200_OK)

                paid_amount = _kobo_to_naira(verify.get("amount"))
                expected = _money(getattr(attempt, "amount", None))

                if paid_amount != expected:
                    _mark_attempt_failed(attempt, payload, reason="Amount mismatch")
                    return Response({"ok": True, "detail": "Amount mismatch"}, status=status.HTTP_200_OK)

                _mark_attempt_verified(attempt, {"verify": verify, "webhook": payload})

                order = attempt.order
                order_id = getattr(order, "id", None) if order else None

                if order and getattr(order, "status", None) != _order_status("STATUS_PAID", "paid"):
                    order.status = _order_status("STATUS_PAID", "paid")
                    if hasattr(order, "paid_at") and not getattr(order, "paid_at", None):
                        order.paid_at = timezone.now()
                        order.save(update_fields=["status", "paid_at"])
                    else:
                        order.save(update_fields=["status"])

            if order_id:
                _finalize_order_to_sale(order_id=order_id)

            return Response({"ok": True, "detail": "Processed"}, status=status.HTTP_200_OK)

        except InsufficientStockError as exc:
            try:
                with transaction.atomic():
                    attempt = PaymentAttempt.objects.filter(reference=reference).select_related("order").first()
                    if attempt and attempt.order:
                        attempt.order.status = _order_status("STATUS_CANCELLED", "cancelled")
                        attempt.order.save(update_fields=["status"])
                        _mark_attempt_failed(attempt, payload, reason=f"Stock error: {exc}")
            except Exception:
                pass
            return Response({"ok": True, "detail": "Stock changed; order cancelled"}, status=status.HTTP_200_OK)

        except (JournalEntryCreationError, IdempotencyError, AccountResolutionError) as exc:
            try:
                attempt = PaymentAttempt.objects.filter(reference=reference).first()
                if attempt and hasattr(attempt, "provider_payload"):
                    attempt.provider_payload = {"warning": str(exc), "payload": payload}
                    attempt.save(update_fields=["provider_payload"])
            except Exception:
                pass
            return Response({"ok": True, "detail": "Paid; posting error logged"}, status=status.HTTP_200_OK)

        except Exception:
            return Response({"ok": True, "detail": "Unhandled error"}, status=status.HTTP_200_OK)
