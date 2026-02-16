# sales/api/viewsets/sale.py

"""
======================================================
PATH: sales/api/viewsets/sale.py
======================================================
SALE VIEWSET (STAFF)

Purpose:
- Provide "Sales History" API for staff UI.
- List + retrieve sales with basic filters.
- Provide Receipt endpoint (print-ready payload for staff UI).
- Provide Refund endpoint (immutable reversal).
- Provide POS Checkout endpoint (store-scoped cart -> immutable sale).

Security:
- Requires IsAuthenticated
- Requires ANY of:
    reports.view_pos
    reports.view_accounting

Refund rules:
- FULL refunds supported (entire sale).
- PARTIAL refunds supported (by items) with strict quantity ceilings.

Checkout rules:
- Store-scoped: store_id is mandatory.
- Backend authoritative for totals & stock.
- Split payments supported.

Receipt rules:
- Receipt is read-only and returns a SaleSerializer payload
  including items + payment_allocations when available.
- Optional store_id query param is accepted (best-effort guard),
  but sale_id remains the primary key.
======================================================
"""

from __future__ import annotations

from datetime import datetime

from django.db.models import Q
from rest_framework import viewsets, status, serializers
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema

from permissions.roles import (
    HasAnyCapability,
    CAP_REPORTS_VIEW_POS,
    CAP_REPORTS_VIEW_ACCOUNTING,
)

from store.models import Store
from pos.models import Cart
from sales.models import Sale
from sales.serializers.sale import SaleSerializer

from sales.services.checkout_orchestrator import (
    checkout_cart,
    EmptyCartError,
    StockValidationError,
    CheckoutError,
    AccountingPostingError,
)

from sales.services.refund_orchestrator import (
    refund_sale_with_stock_restoration,
    RefundOrchestratorError,
)


# ==========================================================
# CHECKOUT INPUT (STAFF)
# ==========================================================

class PaymentAllocationInputSerializer(serializers.Serializer):
    method = serializers.ChoiceField(
        choices=["cash", "bank", "pos", "transfer", "credit"],
    )
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    reference = serializers.CharField(required=False, allow_blank=True, default="")
    note = serializers.CharField(required=False, allow_blank=True, default="")


class CheckoutInputSerializer(serializers.Serializer):
    store_id = serializers.UUIDField(required=True)

    payment_method = serializers.CharField(
        required=False,
        default="cash",
    )

    payment_allocations = PaymentAllocationInputSerializer(
        many=True,
        required=False,
    )


# ==========================================================
# REFUND INPUT
# ==========================================================

class RefundLineSerializer(serializers.Serializer):
    sale_item_id = serializers.CharField(required=True)
    quantity = serializers.IntegerField(min_value=1, required=True)


class RefundInputSerializer(serializers.Serializer):
    items = RefundLineSerializer(many=True, required=False, allow_empty=True)
    reason = serializers.CharField(required=False, allow_blank=True, default="")


# ==========================================================
# VIEWSET
# ==========================================================

class SaleViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = SaleSerializer
    permission_classes = [IsAuthenticated]

    required_any_capabilities = {
        CAP_REPORTS_VIEW_POS,
        CAP_REPORTS_VIEW_ACCOUNTING,
    }

    def get_permissions(self):
        return [IsAuthenticated(), HasAnyCapability()]

    # ======================================================
    # QUERYSET
    # ======================================================

    def get_queryset(self):
        qs = (
            Sale.objects.all()
            .select_related("user")
            .prefetch_related("items", "refund_audit", "payment_allocations")
        )

        # Defensive ordering (supports both fields safely)
        if hasattr(Sale, "completed_at"):
            qs = qs.order_by("-completed_at", "-created_at")
        else:
            qs = qs.order_by("-created_at")

        params = self.request.query_params

        store_id = (params.get("store_id") or "").strip()
        if store_id and hasattr(Sale, "store_id"):
            qs = qs.filter(store_id=store_id)

        status_val = (params.get("status") or "").strip()
        if status_val:
            qs = qs.filter(status=status_val)

        pm = (params.get("payment_method") or "").strip().lower()
        if pm:
            qs = qs.filter(payment_method__iexact=pm)

        q = (params.get("q") or "").strip()
        if q:
            qs = qs.filter(Q(invoice_no__icontains=q))

        def _parse_date(s: str):
            try:
                return datetime.strptime(s, "%Y-%m-%d").date()
            except Exception:
                return None

        date_from = (params.get("date_from") or "").strip()
        if date_from:
            d1 = _parse_date(date_from)
            if d1:
                qs = qs.filter(created_at__date__gte=d1)

        date_to = (params.get("date_to") or "").strip()
        if date_to:
            d2 = _parse_date(date_to)
            if d2:
                qs = qs.filter(created_at__date__lte=d2)

        return qs

    # ======================================================
    # STAFF RECEIPT (CANONICAL)
    # GET /api/sales/sales/:id/receipt/
    # ======================================================

    @extend_schema(
        responses={200: SaleSerializer},
        description=(
            "Return a print-ready receipt payload for a sale. "
            "Includes items + split payment allocations when available."
        ),
    )
    @action(detail=True, methods=["get"], url_path="receipt")
    def receipt(self, request, pk=None):
        sale: Sale = self.get_object()

        # Best-effort guard for multi-store: if store_id is provided and Sale has store_id, enforce match.
        store_id = (request.query_params.get("store_id") or "").strip()
        if store_id and hasattr(sale, "store_id"):
            try:
                if str(getattr(sale, "store_id", "")) != str(store_id):
                    return Response(
                        {"detail": "Sale does not belong to the provided store_id."},
                        status=status.HTTP_404_NOT_FOUND,
                    )
            except Exception:
                # If anything about comparison is weird, don't crash receipt.
                pass

        return Response(SaleSerializer(sale).data, status=status.HTTP_200_OK)

    # ======================================================
    # STAFF POS CHECKOUT
    # ======================================================

    @extend_schema(
        request=CheckoutInputSerializer,
        responses={201: SaleSerializer},
    )
    @action(detail=False, methods=["post"], url_path="checkout")
    def checkout(self, request):
        ser = CheckoutInputSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        store_id = ser.validated_data["store_id"]
        payment_method = ser.validated_data.get("payment_method", "cash")
        payment_allocations = ser.validated_data.get("payment_allocations")

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
        except Cart.DoesNotExist:
            return Response(
                {"detail": "No active cart found for this store."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
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

        except EmptyCartError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        except StockValidationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)

        except (CheckoutError, AccountingPostingError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        except Exception as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    # ======================================================
    # REFUND (FULL or PARTIAL)
    # ======================================================

    @extend_schema(
        request=RefundInputSerializer,
        responses={200: serializers.DictField()},
    )
    @action(detail=True, methods=["post"], url_path="refund")
    def refund(self, request, pk=None):
        sale: Sale = self.get_object()

        ser = RefundInputSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        items = ser.validated_data.get("items") or []
        reason = (ser.validated_data.get("reason") or "").strip()

        try:
            refunded_sale = refund_sale_with_stock_restoration(
                sale=sale,
                user=request.user,
                refund_reason=reason or None,
                items=items or None,
            )

            audit = getattr(refunded_sale, "refund_audit", None)
            refund_no = None
            if audit:
                refund_no = getattr(audit, "refund_no", None) or str(getattr(audit, "id", "")) or None

            return Response(
                {
                    "refund_no": refund_no,
                    "sale_id": str(refunded_sale.id),
                    "status": refunded_sale.status,
                    "detail": "Refund processed successfully.",
                    "mode": "partial" if items else "full",
                },
                status=status.HTTP_200_OK,
            )

        except RefundOrchestratorError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        except serializers.ValidationError as exc:
            return Response({"detail": exc.detail}, status=status.HTTP_400_BAD_REQUEST)

        except Exception as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
