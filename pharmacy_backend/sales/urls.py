# pharmacy_backend/sales/urls.py

from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import SaleViewSet, SaleCreateView

router = DefaultRouter()
router.register(r"", SaleViewSet, basename="sales")

urlpatterns = [
    # -------------------------------
    # Sales reporting (READ-ONLY)
    # -------------------------------
    path("", include(router.urls)),

    # -------------------------------
    # POS Checkout (WRITE)
    # -------------------------------
    path(
        "pos/checkout/",
        SaleCreateView.as_view(),
        name="pos-checkout",
    ),
]
