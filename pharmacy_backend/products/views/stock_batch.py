"""
======================================================
PATH: products/views/stock_batch.py
======================================================
STOCK BATCH VIEWSET (PHASE 2)

Purpose:
- Manage StockBatch metadata + controlled inventory operations:
  receive / adjust / expire + movement reports.
- Enforce service-managed quantity rules and audit-safe StockMovement logging.

HOTSPRINT UPGRADE (PURCHASE-LED STOCKING):
- Creating a StockBatch represents a PURCHASE RECEIPT (not just metadata).
- Therefore: unit_cost is REQUIRED on create for new batches.
- Legacy batches with unit_cost=NULL may exist, but should be fixed via migration/backfill,
  not via the normal create endpoint.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from django.db import transaction
from django.utils import timezone

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from permissions.roles import (
    HasCapability,
    HasAnyCapability,
    CAP_INVENTORY_VIEW,
    CAP_INVENTORY_EDIT,
    CAP_INVENTORY_ADJUST,
)

from products.models import StockBatch, StockMovement, Product
from products.serializers.stock_batch import StockBatchSerializer

# Canonical purchase-led intake (creates batch + receipt movement)
from products.services.stock_intake import intake_stock

# Existing services (actions)
from products.services.inventory import receive_stock, adjust_stock, expire_stock


class StockBatchViewSet(viewsets.ModelViewSet):
    """
    Stock batch endpoints.

    RULES:
    - Creation is PURCHASE-LED:
        create() uses intake_stock() (creates batch + receipt movement).
        We do NOT allow creating "metadata-only" batches via POST anymore.
    - Quantity mutation is SERVICE-managed (never direct edits).
    - PATCH allowed ONLY for metadata fields (batch_number, expiry_date).
    - Deletion is admin-only (model also blocks delete if movements exist).
    """

    serializer_class = StockBatchSerializer
    permission_classes = [IsAuthenticated]

    # These are read by your HasCapability / HasAnyCapability classes
    required_capability = None
    required_any_capabilities = None

    def get_permissions(self):
        # IMPORTANT: reset per request to avoid state leaking between actions
        self.required_capability = None
        self.required_any_capabilities = None

        if self.action in {"list", "retrieve", "movement_report", "expiring_soon"}:
            self.required_any_capabilities = {
                CAP_INVENTORY_VIEW,
                CAP_INVENTORY_EDIT,
                CAP_INVENTORY_ADJUST,
            }
            return [IsAuthenticated(), HasAnyCapability()]

        if self.action in {"create", "partial_update", "receive"}:
            self.required_capability = CAP_INVENTORY_EDIT
            return [IsAuthenticated(), HasCapability()]

        if self.action in {"adjust", "expire"}:
            self.required_capability = CAP_INVENTORY_ADJUST
            return [IsAuthenticated(), HasCapability()]

        return [IsAuthenticated()]

    def get_queryset(self):
        qs = (
            StockBatch.objects.select_related("product", "product__store")
            .order_by("expiry_date", "created_at")
        )

        store_id = (self.request.query_params.get("store_id") or "").strip()
        if store_id:
            # store is on StockBatch in your model
            qs = qs.filter(store_id=store_id)

        product_id = (self.request.query_params.get("product_id") or "").strip()
        if product_id:
            qs = qs.filter(product_id=product_id)

        include_inactive = (self.request.query_params.get("include_inactive") or "true").strip().lower() in (
            "1", "true", "yes"
        )
        if not include_inactive:
            qs = qs.filter(is_active=True)

        return qs

    # -------------------------------------------------
    # CREATE (purchase-led intake)
    # -------------------------------------------------
    @transaction.atomic
    def create(self, request, *args, **kwargs):
        """
        POST /api/products/stock-batches/

        Purchase-led intake:
        - Creates StockBatch + StockMovement(RECEIPT) atomically.
        - unit_cost is REQUIRED.
        - batch_number is OPTIONAL (service auto-generates if missing/blank).
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        v = serializer.validated_data

        product_id = v.get("product_id", None)
        if not product_id:
            return Response({"detail": "product_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Enforce active product only
            product = Product.objects.get(id=product_id, is_active=True)
        except Product.DoesNotExist:
            return Response({"detail": "Invalid or inactive product id"}, status=status.HTTP_400_BAD_REQUEST)

        # Optional explicit store override (frontend can pass store_id)
        # If omitted, intake_stock will resolve from product.store.
        store_id = (request.data.get("store_id") or "").strip() or getattr(product, "store_id", None)

        try:
            batch = intake_stock(
                product=product,
                quantity_received=v.get("quantity_received"),
                unit_cost=v.get("unit_cost"),
                expiry_date=v.get("expiry_date"),
                batch_number=v.get("batch_number"),  # may be None; service will generate
                user=request.user,
                store=store_id,
                update_product_price=False,
            )
        except Exception as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        batch.refresh_from_db()
        return Response(self.get_serializer(batch).data, status=status.HTTP_201_CREATED)

    # -------------------------------------------------
    # UPDATE (restricted)
    # -------------------------------------------------
    def update(self, request, *args, **kwargs):
        return Response(
            {
                "detail": (
                    "PUT is not allowed for StockBatch. "
                    "Use PATCH for metadata only (batch_number, expiry_date). "
                    "Quantity changes must go through actions: receive/adjust/expire."
                )
            },
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    def partial_update(self, request, *args, **kwargs):
        """
        PATCH /api/products/stock-batches/{id}/

        Metadata-only updates.

        Allowed:
        - batch_number
        - expiry_date
        """
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        try:
            batch = serializer.save()
        except Exception as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(self.get_serializer(batch).data, status=status.HTTP_200_OK)

    # -------------------------------------------------
    # DELETE (admin-only)
    # -------------------------------------------------
    def destroy(self, request, *args, **kwargs):
        if not request.user.is_authenticated or getattr(request.user, "role", None) != "admin":
            return Response({"detail": "Only admins can delete stock batches."}, status=status.HTTP_403_FORBIDDEN)
        return super().destroy(request, *args, **kwargs)

    # -------------------------------------------------
    # ACTIONS: receive / adjust / expire
    # -------------------------------------------------
    @action(detail=True, methods=["post"], url_path="receive")
    @transaction.atomic
    def receive(self, request, pk=None):
        """
        POST /api/products/stock-batches/{id}/receive/

        Backward-compatibility:
        - If legacy batches were created without receipt, this will initialize inventory ONCE.
        - If already received, idempotently returns.
        """
        batch = self.get_object()
        try:
            receive_stock(batch=batch, user=request.user)
        except Exception as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        batch.refresh_from_db()
        return Response(self.get_serializer(batch).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="adjust")
    @transaction.atomic
    def adjust(self, request, pk=None):
        batch = self.get_object()

        raw_delta = (request.data or {}).get("quantity_delta")
        try:
            quantity_delta = int(raw_delta)
        except (TypeError, ValueError):
            return Response({"detail": "quantity_delta must be an integer"}, status=status.HTTP_400_BAD_REQUEST)

        if quantity_delta == 0:
            return Response({"detail": "quantity_delta cannot be 0"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            adjust_stock(batch=batch, quantity_delta=quantity_delta, user=request.user)
        except Exception as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        batch.refresh_from_db()
        return Response(self.get_serializer(batch).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="expire")
    @transaction.atomic
    def expire(self, request, pk=None):
        batch = self.get_object()

        try:
            expire_stock(batch=batch, user=request.user)
        except Exception as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        batch.refresh_from_db()
        return Response(self.get_serializer(batch).data, status=status.HTTP_200_OK)

    # -------------------------------------------------
    # REPORT: Stock movements (filterable)
    # -------------------------------------------------
    @action(detail=False, methods=["get"], url_path="movements/report")
    def movement_report(self, request):
        qs = StockMovement.objects.select_related("product", "batch", "sale", "performed_by")

        product_id = (request.query_params.get("product_id") or "").strip()
        store_id = (request.query_params.get("store_id") or "").strip()
        reason = (request.query_params.get("reason") or "").strip()
        movement_type = (request.query_params.get("movement_type") or "").strip()
        sale_id = (request.query_params.get("sale_id") or "").strip()
        date_from = (request.query_params.get("date_from") or "").strip()
        date_to = (request.query_params.get("date_to") or "").strip()

        if product_id:
            qs = qs.filter(product_id=product_id)
        if store_id:
            qs = qs.filter(product__store_id=store_id)
        if reason:
            qs = qs.filter(reason=reason)
        if movement_type:
            qs = qs.filter(movement_type=movement_type)
        if sale_id:
            qs = qs.filter(sale_id=sale_id)

        def _parse_date(s: str):
            try:
                return datetime.strptime(s, "%Y-%m-%d").date()
            except Exception:
                return None

        if date_from:
            d1 = _parse_date(date_from)
            if not d1:
                return Response({"detail": "date_from must be YYYY-MM-DD"}, status=400)
            qs = qs.filter(created_at__date__gte=d1)

        if date_to:
            d2 = _parse_date(date_to)
            if not d2:
                return Response({"detail": "date_to must be YYYY-MM-DD"}, status=400)
            qs = qs.filter(created_at__date__lte=d2)

        qs = qs.order_by("-created_at")[:500]

        results = []
        for m in qs:
            results.append(
                {
                    "id": str(m.id),
                    "created_at": m.created_at.isoformat(),
                    "product_id": str(m.product_id),
                    "product_name": getattr(m.product, "name", ""),
                    "batch_id": str(m.batch_id),
                    "batch_number": getattr(m.batch, "batch_number", ""),
                    "expiry_date": getattr(m.batch, "expiry_date", None),
                    "movement_type": m.movement_type,
                    "reason": m.reason,
                    "quantity": int(m.quantity or 0),
                    "unit_cost_snapshot": str(getattr(m, "unit_cost_snapshot", "") or ""),
                    "total_cost": str(getattr(m, "total_cost", "") or ""),
                    "sale_id": str(m.sale_id) if m.sale_id else None,
                    "performed_by": str(m.performed_by_id) if m.performed_by_id else None,
                }
            )

        return Response({"count": len(results), "results": results}, status=200)

    # -------------------------------------------------
    # ALERT: Expiring soon (active batches)
    # -------------------------------------------------
    @action(detail=False, methods=["get"], url_path="alerts/expiring-soon")
    def expiring_soon(self, request):
        raw_days = (request.query_params.get("days") or "30").strip()
        try:
            days = int(raw_days)
            if days < 0:
                raise ValueError
        except ValueError:
            return Response({"detail": "days must be a non-negative integer"}, status=400)

        today = timezone.localdate()
        cutoff = today + timedelta(days=days)

        qs = self.get_queryset().filter(
            is_active=True,
            expiry_date__gte=today,
            expiry_date__lte=cutoff,
        )

        data = self.get_serializer(qs, many=True).data
        return Response({"count": len(data), "results": data})
