# PATH: public/urls.py

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
- GET  /api/public/payments/paystack/callback/   <-- NEW
"""

from django.urls import path

from public.views.catalog import PublicCatalogView
from public.views.checkout import PublicCheckoutView, PublicReceiptView
from public.views.order import PublicOrderInitiateView, PublicOrderStatusView
from public.views.paystack_webhook import PaystackWebhookView
from public.views.paystack_callback import PaystackCallbackView  # ✅ NEW

app_name = "public"

urlpatterns = [
    # Legacy V1
    path("checkout/", PublicCheckoutView.as_view(), name="public-checkout"),
    path("receipt/<uuid:sale_id>/", PublicReceiptView.as_view(), name="public-receipt"),

    # Public catalog
    path("catalog/", PublicCatalogView.as_view(), name="public-catalog"),

    # Phase 4 (Safe flow)
    path("order/initiate/", PublicOrderInitiateView.as_view(), name="public-order-initiate"),
    path("order/<uuid:order_id>/", PublicOrderStatusView.as_view(), name="public-order-status"),

    # Paystack
    path("payments/paystack/webhook/", PaystackWebhookView.as_view(), name="paystack-webhook"),
    path("payments/paystack/callback/", PaystackCallbackView.as_view(), name="paystack-callback"),  # ✅ NEW
]