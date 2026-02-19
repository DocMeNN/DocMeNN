# public/views/catalog.py
"""
PUBLIC CATALOG (ONLINE STORE)

GET /api/public/catalog/?store_id=<uuid>

Rules:
- AllowAny (public)
- Store-scoped (store_id required)
- Backend is source of truth for product data
- Does NOT expose internal cost data

Security hardening:
- Throttle to reduce scraping/abuse (cost-effective)
"""

from __future__ import annotations

from django.core.exceptions import FieldDoesNotExist
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import serializers, status
from rest_framework.parsers import JSONParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from products.models import Product
from store.models import Store


class PublicCatalogThrottle(AnonRateThrottle):
    scope = "public_catalog"


class PublicCatalogQuerySerializer(serializers.Serializer):
    store_id = serializers.UUIDField(required=True)


class PublicCatalogItemSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    unit_price = serializers.DecimalField(max_digits=12, decimal_places=2)
    is_active = serializers.BooleanField()


class PublicCatalogView(APIView):
    """
    GET /api/public/catalog/?store_id=<uuid>
    """

    permission_classes = [AllowAny]
    parser_classes = [JSONParser]
    throttle_classes = [PublicCatalogThrottle]

    @extend_schema(
        tags=["Public"],
        parameters=[
            OpenApiParameter(
                name="store_id",
                type=str,
                location=OpenApiParameter.QUERY,
                required=True,
                description="Store UUID (required). Catalog is store-scoped.",
            ),
        ],
        responses={
            200: PublicCatalogItemSerializer(many=True),
            400: OpenApiResponse(description="Bad request / validation error"),
            404: OpenApiResponse(description="Store not found"),
            429: OpenApiResponse(description="Rate limited"),
        },
        description="Public product catalog for a store (AllowAny).",
    )
    def get(self, request, *args, **kwargs):
        qs = PublicCatalogQuerySerializer(data=request.query_params)
        qs.is_valid(raise_exception=True)
        store_id = qs.validated_data["store_id"]

        store = Store.objects.filter(id=store_id, is_active=True).first()
        if not store:
            return Response(
                {"detail": "Store not found"}, status=status.HTTP_404_NOT_FOUND
            )

        products = Product.objects.filter(is_active=True)

        # Store scoping (supports either Product.store FK or Product.store_id field)
        try:
            Product._meta.get_field("store")
            products = products.filter(store=store)
        except FieldDoesNotExist:
            try:
                Product._meta.get_field("store_id")
                products = products.filter(store_id=store.id)
            except FieldDoesNotExist:
                pass

        products = products.order_by("name")

        payload = [
            {
                "id": p.id,
                "name": getattr(p, "name", ""),
                "unit_price": getattr(p, "unit_price", 0),
                "is_active": bool(getattr(p, "is_active", True)),
            }
            for p in products
        ]

        return Response(payload, status=status.HTTP_200_OK)
