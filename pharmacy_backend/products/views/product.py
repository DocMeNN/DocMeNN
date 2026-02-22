# products/views/product.py

"""
PRODUCT VIEWSET

Purpose:
- Staff product management endpoints (CRUD + alerts)
- Public product browsing endpoint for the Online Store (AllowAny)

Key rule alignment:
- Store-aware + migration-safe NULL-store fallback for stock totals.
- Public endpoint is read-only and returns ONLY active products.
"""

from datetime import timedelta

from django.db.models import Case, F, IntegerField, Q, Sum, When
from django.db.models.functions import Coalesce
from django.utils import timezone
from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
)
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from permissions.roles import IsPharmacistOrAdmin
from products.models import Product, StockBatch
from products.serializers.product import ProductSerializer


class ProductViewSet(viewsets.ModelViewSet):
    """
    Product endpoints.

    Staff:
    - CRUD
    - Low stock alerts
    - Expiring soon alerts

    Public:
    - GET /products/products/public/?store_id=<uuid>&q=<search>
    """

    serializer_class = ProductSerializer
    permission_classes = [IsAuthenticated, IsPharmacistOrAdmin]

    def _get_store_id(self):
        return (self.request.query_params.get("store_id") or "").strip() or None

    def _stockbatch_has_store_fk(self) -> bool:
        try:
            StockBatch._meta.get_field("store")
            return True
        except Exception:
            return False

    def get_queryset(self):
        """
        Annotate total_stock to avoid N+1 on product lists.

        Stock rules:
        - only active batches
        - only non-expired batches (expiry_date >= today)
        - store-aware (if store_id is supplied)
        - fallback to NULL-store batches ONLY if no store batches exist for that product
        """
        today = timezone.localdate()
        store_id = self._get_store_id()

        qs = Product.objects.select_related("category", "store")

        # If store_id is supplied, scope products to that store (strongest guarantee)
        if store_id:
            qs = qs.filter(store_id=store_id)

        has_batch_store_fk = self._stockbatch_has_store_fk()

        # If StockBatch doesn't have store FK, we can only rely on product.store scoping.
        if store_id and not has_batch_store_fk:
            base_filter = Q(stock_batches__is_active=True) & Q(
                stock_batches__expiry_date__gte=today
            )
            return qs.annotate(
                total_stock=Coalesce(
                    Sum("stock_batches__quantity_remaining", filter=base_filter),
                    0,
                )
            ).order_by("-created_at")

        # ---------------------------------------------------------
        # Store-aware + NULL-store fallback (matches checkout logic)
        # ---------------------------------------------------------
        if store_id and has_batch_store_fk:
            store_filter = (
                Q(stock_batches__is_active=True)
                & Q(stock_batches__expiry_date__gte=today)
                & Q(stock_batches__store_id=store_id)
            )

            null_store_filter = (
                Q(stock_batches__is_active=True)
                & Q(stock_batches__expiry_date__gte=today)
                & Q(stock_batches__store__isnull=True)
            )

            store_total = Coalesce(
                Sum("stock_batches__quantity_remaining", filter=store_filter),
                0,
            )

            null_total = Coalesce(
                Sum("stock_batches__quantity_remaining", filter=null_store_filter),
                0,
            )

            # Count of store batches (not qty) — used only to decide whether fallback applies
            store_batch_count = Coalesce(
                Sum(
                    Case(
                        When(store_filter, then=1),
                        default=0,
                        output_field=IntegerField(),
                    )
                ),
                0,
            )

            return (
                qs.annotate(
                    _store_batch_count=store_batch_count,
                    _store_total=store_total,
                    _null_total=null_total,
                )
                .annotate(
                    total_stock=Case(
                        When(_store_batch_count__gt=0, then=F("_store_total")),
                        default=F("_null_total"),
                        output_field=IntegerField(),
                    )
                )
                .order_by("-created_at")
            )

        # No store_id supplied => global totals across all batches
        base_filter = Q(stock_batches__is_active=True) & Q(
            stock_batches__expiry_date__gte=today
        )
        return qs.annotate(
            total_stock=Coalesce(
                Sum("stock_batches__quantity_remaining", filter=base_filter),
                0,
            )
        ).order_by("-created_at")

    # -----------------------------
    # Public Online Store (AllowAny)
    # -----------------------------
    @extend_schema(
        tags=["Public"],
        parameters=[
            OpenApiParameter(
                name="store_id",
                type=str,
                location=OpenApiParameter.QUERY,
                required=True,
                description="Store UUID (required). Public browsing is store-scoped.",
            ),
            OpenApiParameter(
                name="q",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Optional search query (name, sku, barcode if present).",
            ),
        ],
        responses={
            200: OpenApiResponse(
                response=ProductSerializer(many=True),
                description="List of active products",
            ),
            400: OpenApiResponse(description="Missing or invalid store_id"),
        },
        description="Public storefront browsing (AllowAny). Requires store_id for correctness.",
    )
    @action(
        detail=False,
        methods=["get"],
        url_path="public",
        permission_classes=[AllowAny],
    )
    def public(self, request):
        """
        GET /api/products/products/public/?store_id=<uuid>&q=<text>
        """
        store_id = (request.query_params.get("store_id") or "").strip()
        if not store_id:
            return Response(
                {"detail": "store_id is required for public shop browsing (V1)."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        q = (request.query_params.get("q") or "").strip()

        qs = self.get_queryset().filter(is_active=True)

        if q:
            # barcode may not exist on Product; keep safe
            filter_q = Q(name__icontains=q) | Q(sku__icontains=q)
            if hasattr(Product, "barcode"):
                filter_q = filter_q | Q(barcode__icontains=q)
            qs = qs.filter(filter_q)

        data = self.get_serializer(qs, many=True).data
        return Response({"count": len(data), "results": data}, status=status.HTTP_200_OK)

    # -----------------------------
    # Admin-only delete (safe)
    # -----------------------------
    def destroy(self, request, *args, **kwargs):
        if (
            not request.user.is_authenticated
            or getattr(request.user, "role", None) != "admin"
        ):
            return Response(
                {"detail": "Only admins can delete products."},
                status=status.HTTP_403_FORBIDDEN,
            )
        return super().destroy(request, *args, **kwargs)

    # -----------------------------
    # Alerts: Low stock
    # -----------------------------
    @action(detail=False, methods=["get"], url_path="alerts/low-stock")
    def low_stock_alerts(self, request):
        """
        GET /products/products/alerts/low-stock/

        Optional query params:
        - threshold=<int>
        - include_inactive=true|false (default false)
        - store_id=<uuid> (optional store filter)
        """
        qs = self.get_queryset()

        include_inactive = (
            request.query_params.get("include_inactive") or ""
        ).strip().lower() in ("1", "true", "yes")

        if not include_inactive:
            qs = qs.filter(is_active=True)

        raw_threshold = (request.query_params.get("threshold") or "").strip()

        if raw_threshold:
            try:
                threshold = int(raw_threshold)
                if threshold < 0:
                    raise ValueError
            except ValueError:
                return Response(
                    {"detail": "threshold must be a non-negative integer"}, status=400
                )

            qs = qs.filter(total_stock__lte=threshold)
        else:
            qs = qs.filter(total_stock__lte=F("low_stock_threshold"))

        data = self.get_serializer(qs, many=True).data
        return Response({"count": len(data), "results": data})

    # -----------------------------
    # Alerts: Expiring soon (product-level)
    # -----------------------------
    @action(detail=False, methods=["get"], url_path="alerts/expiring-soon")
    def expiring_soon(self, request):
        """
        GET /products/products/alerts/expiring-soon/?days=30&store_id=<uuid>

        Returns products that have at least one ACTIVE batch expiring within N days.
        """
        raw_days = (request.query_params.get("days") or "30").strip()
        try:
            days = int(raw_days)
            if days < 0:
                raise ValueError
        except ValueError:
            return Response(
                {"detail": "days must be a non-negative integer"}, status=400
            )

        today = timezone.localdate()
        cutoff = today + timedelta(days=days)
        store_id = self._get_store_id()

        batch_qs = StockBatch.objects.filter(
            is_active=True,
            expiry_date__gte=today,
            expiry_date__lte=cutoff,
        ).select_related("product")

        if store_id:
            if self._stockbatch_has_store_fk():
                batch_qs = batch_qs.filter(Q(store_id=store_id) | Q(store__isnull=True))
            else:
                batch_qs = batch_qs.filter(product__store_id=store_id)

        product_ids = batch_qs.values_list("product_id", flat=True).distinct()
        qs = self.get_queryset().filter(id__in=list(product_ids))

        data = self.get_serializer(qs, many=True).data
        return Response({"count": len(data), "results": data})