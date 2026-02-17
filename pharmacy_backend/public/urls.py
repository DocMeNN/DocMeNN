# public/urls.py
"""
PUBLIC API URLS (ONLINE STORE)

Base path (mounted in backend/urls.py):
    /api/public/

Legacy V1:
- POST /api/public/checkout/
- GET  /api/public/receipt/<sale_id>/

Phase 4 (Paystack-safe):
- POST /api/public/order/initiate/
- GET  /api/public/order/<order_id>/
- POST /api/public/payments/paystack/webhook/
- GET  /api/public/payments/paystack/callback/

Security hardening:
- Allow disabling legacy checkout in production via env:
    PUBLIC_LEGACY_CHECKOUT_ENABLED=False
  (default True for backward compatibility)

Best practice:
- For card payments, legacy checkout should be OFF in production.
  Use order/initiate + webhook finalization only.
"""

from __future__ import annotations

from django.conf import settings
from django.urls import path

from public.views.catalog import PublicCatalogView
from public.views.checkout import PublicCheckoutView, PublicReceiptView
from public.views.order import PublicOrderInitiateView, PublicOrderStatusView
from public.views.paystack_webhook import PaystackWebhookView
from public.views.paystack_callback import PaystackCallbackView

app_name = "public"

PUBLIC_LEGACY_CHECKOUT_ENABLED = bool(
    getattr(settings, "PUBLIC_LEGACY_CHECKOUT_ENABLED", True)
)

urlpatterns = [
    # Public catalog
    path("catalog/", PublicCatalogView.as_view(), name="public-catalog"),

    # Phase 4 (Safe flow)
    path("order/initiate/", PublicOrderInitiateView.as_view(), name="public-order-initiate"),
    path("order/<uuid:order_id>/", PublicOrderStatusView.as_view(), name="public-order-status"),

    # Paystack
    path("payments/paystack/webhook/", PaystackWebhookView.as_view(), name="paystack-webhook"),
    path("payments/paystack/callback/", PaystackCallbackView.as_view(), name="paystack-callback"),
]

# Legacy V1 (optional)
if PUBLIC_LEGACY_CHECKOUT_ENABLED:
    urlpatterns = [
        path("checkout/", PublicCheckoutView.as_view(), name="public-checkout"),
        path("receipt/<uuid:sale_id>/", PublicReceiptView.as_view(), name="public-receipt"),
    ] + urlpatterns
