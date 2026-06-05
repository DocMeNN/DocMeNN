from django.urls import path
from .views import (
    POSCartView,
    AddToCartView,
    RemoveFromCartView,
    CheckoutView
)

urlpatterns = [
    path("cart/", POSCartView.as_view(), name="pos-cart"),
    path("cart/add/", AddToCartView.as_view(), name="pos-add"),
    path("cart/remove/<uuid:pk>/", RemoveFromCartView.as_view(), name="pos-remove"),
    path("checkout/", CheckoutView.as_view(), name="pos-checkout"),
]
