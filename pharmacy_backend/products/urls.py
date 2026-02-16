# products/urls.py

"""
PRODUCTS URLS

Purpose:
- Register product domain routes under /api/products/
- Includes viewset actions like:
    /products/products/public/   (AllowAny)
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from products.views import ProductViewSet, StockBatchViewSet
from products.views.category import CategoryViewSet

router = DefaultRouter()

router.register(r"categories", CategoryViewSet, basename="categories")
router.register(r"products", ProductViewSet, basename="products")
router.register(r"stock-batches", StockBatchViewSet, basename="stock-batches")

urlpatterns = [
    path("", include(router.urls)),
]
