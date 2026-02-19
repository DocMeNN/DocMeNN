"""
PATH: pos/urls.py

POS URLS (PHASE 1)

Purpose:
- POS health check
- Cart lifecycle
- Cart item operations
- Cart checkout (finalizes to Sale via checkout orchestrator)
"""

from django.urls import path

from pos.views.api import (
    POSHealthCheckView,
    ActiveCartView,
    AddCartItemView,
    UpdateCartItemView,
    RemoveCartItemView,
    ClearCartView,
    CheckoutCartView,
)

app_name = "pos"

urlpatterns = [
    path("health/", POSHealthCheckView.as_view(), name="health"),

    path("cart/", ActiveCartView.as_view(), name="active-cart"),
    path("cart/clear/", ClearCartView.as_view(), name="clear-cart"),

    path("cart/items/add/", AddCartItemView.as_view(), name="add-cart-item"),
    path("cart/items/<uuid:item_id>/update/", UpdateCartItemView.as_view(), name="update-cart-item"),
    path("cart/items/<uuid:item_id>/remove/", RemoveCartItemView.as_view(), name="remove-cart-item"),

    path("checkout/", CheckoutCartView.as_view(), name="checkout"),
]
