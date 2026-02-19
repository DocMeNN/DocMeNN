# sales/public_urls.py

"""
PUBLIC API URLS (ONLINE STORE)

Base path (mounted in backend/urls.py):
    /api/public/

Endpoints:
- POST /api/public/checkout/   -> public checkout (AllowAny)
- GET  /api/public/receipt/<sale_id>/ -> minimal receipt fetch (AllowAny)

Rules:
- Store-scoped (store_id required)
- Uses same stock FIFO + ledger posting guarantees as POS
"""

from django.urls import path

from sales.views.public_checkout import PublicCheckoutView, PublicReceiptView

app_name = "public_api"

urlpatterns = [
    path("checkout/", PublicCheckoutView.as_view(), name="public-checkout"),
    path("receipt/<uuid:sale_id>/", PublicReceiptView.as_view(), name="public-receipt"),
]
