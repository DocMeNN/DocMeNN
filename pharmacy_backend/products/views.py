# pharmacy_backend/products/views.py

import csv
import io
from datetime import timedelta

from django.db.models import Q, Sum
from django.http import HttpResponse
from django.utils.timezone import now

from rest_framework import viewsets, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.parsers import JSONParser, MultiPartParser, FormParser

from permissions.roles import IsPharmacistOrAdmin
from .models import Product, StockBatch
from .serializers import ProductSerializer, StockBatchSerializer


# ============================================================
# PRODUCT
# ============================================================

class ProductViewSet(viewsets.ModelViewSet):
    """
    Product CRUD ViewSet

    Features:
    - Inventory-aware listing
    - Bulk upload (JSON / CSV)
    - CSV export
    - Stock alerts (low stock, near expiry)
    """

    serializer_class = ProductSerializer
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    # -------------------- PERMISSIONS --------------------
    def get_permissions(self):
        if self.action in ["list", "retrieve"]:
            return [IsAuthenticated()]
        return [IsPharmacistOrAdmin()]

    # -------------------- QUERYSET --------------------
    def get_queryset(self):
        qs = (
            Product.objects.select_related("category")
            .annotate(
                total_stock=Sum(
                    "stock_batches__quantity_remaining",
                    filter=Q(stock_batches__is_active=True),
                )
            )
            .order_by("-created_at")
        )

        params = self.request.query_params

        search = params.get("search")
        category_id = params.get("category_id")
        price_min = params.get("price_min")
        price_max = params.get("price_max")
        created_from = params.get("created_from")
        created_to = params.get("created_to")

        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(sku__icontains=search))

        if category_id:
            qs = qs.filter(category_id=category_id)

        if price_min:
            qs = qs.filter(unit_price__gte=price_min)

        if price_max:
            qs = qs.filter(unit_price__lte=price_max)

        if created_from:
            qs = qs.filter(created_at__date__gte=created_from)

        if created_to:
            qs = qs.filter(created_at__date__lte=created_to)

        return qs

    # -------------------- BULK CREATE --------------------
    @action(detail=False, methods=["post"], url_path="bulk-create")
    def bulk_create(self, request):
        products_data = []

        if "file" in request.FILES:
            file = request.FILES["file"]

            if not file.name.endswith(".csv"):
                return Response(
                    {"error": "Only CSV files are allowed"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            decoded_file = file.read().decode("utf-8")
            reader = csv.DictReader(io.StringIO(decoded_file))

            required_headers = {"sku", "name", "unit_price"}
            if not required_headers.issubset(reader.fieldnames or []):
                return Response(
                    {
                        "error": "CSV missing required headers",
                        "required": list(required_headers),
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            for row in reader:
                products_data.append(
                    {
                        "sku": row.get("sku"),
                        "name": row.get("name"),
                        "unit_price": row.get("unit_price"),
                        "category_id": row.get("category_id") or None,
                    }
                )
        else:
            products_data = request.data.get("products")

            if not isinstance(products_data, list):
                return Response(
                    {"error": "Expected a list of products"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        serializer = ProductSerializer(data=products_data, many=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(
            {
                "message": "Bulk product upload successful",
                "total_uploaded": len(products_data),
            },
            status=status.HTTP_201_CREATED,
        )

    # -------------------- CSV EXPORT --------------------
    @action(detail=False, methods=["get"], url_path="export-csv")
    def export_csv(self, request):
        queryset = self.filter_queryset(self.get_queryset())

        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="products.csv"'

        writer = csv.writer(response)
        writer.writerow(
            [
                "id",
                "sku",
                "name",
                "category",
                "unit_price",
                "total_stock",
                "created_at",
            ]
        )

        for product in queryset:
            writer.writerow(
                [
                    product.id,
                    product.sku,
                    product.name,
                    product.category.name if product.category else "",
                    product.unit_price,
                    product.total_stock or 0,
                    product.created_at,
                ]
            )

        return response

    # ==================== ALERTS ====================

    @action(detail=False, methods=["get"], url_path="alerts/low-stock")
    def low_stock_alerts(self, request):
        threshold = int(request.query_params.get("threshold", 10))

        products = self.get_queryset().filter(
            total_stock__lte=threshold
        )

        return Response(
            {
                "threshold": threshold,
                "count": products.count(),
                "products": ProductSerializer(products, many=True).data,
            }
        )

    @action(detail=False, methods=["get"], url_path="alerts/expiring-soon")
    def expiry_alerts(self, request):
        days = int(request.query_params.get("days", 30))
        expiry_limit = now().date() + timedelta(days=days)

        batches = (
            StockBatch.objects.select_related("product")
            .filter(
                is_active=True,
                expiry_date__lte=expiry_limit,
                quantity_remaining__gt=0,
            )
            .order_by("expiry_date")
        )

        return Response(
            {
                "days": days,
                "count": batches.count(),
                "batches": StockBatchSerializer(batches, many=True).data,
            }
        )


# ============================================================
# STOCK BATCH
# ============================================================

class StockBatchViewSet(viewsets.ModelViewSet):
    """
    Inventory / Stock Receiving ViewSet
    """

    serializer_class = StockBatchSerializer

    def get_permissions(self):
        return [IsPharmacistOrAdmin()]

    def get_queryset(self):
        qs = StockBatch.objects.select_related("product")

        params = self.request.query_params

        product_id = params.get("product_id")
        expiry_before = params.get("expiry_before")
        is_active = params.get("is_active")

        if product_id:
            qs = qs.filter(product_id=product_id)

        if expiry_before:
            qs = qs.filter(expiry_date__lte=expiry_before)

        if is_active is not None:
            qs = qs.filter(is_active=is_active.lower() == "true")

        return qs.order_by("expiry_date", "created_at")
