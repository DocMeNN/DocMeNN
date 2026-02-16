# sales/api/urls.py

"""
SALES API URLS (CANONICAL)

Rules:
- Explicit non-PK routes (like "checkout") MUST be registered BEFORE router URLs,
  otherwise the router will treat "checkout" as a <pk> and you'll get 405.

Provides:
- Staff checkout:
    POST /api/sales/checkout/

- Staff endpoints:
    /api/sales/sales/         (canonical list)
    /api/sales/sales/<uuid>/  (canonical retrieve)

- Legacy alias (kept for older frontend calls):
    /api/sales/               (list alias)
    /api/sales/<uuid>/        (retrieve alias)

- ✅ POS Reports (Admin-only):
    GET /api/sales/reports/daily/?date=YYYY-MM-DD
    GET /api/sales/reports/cash-recon/?date=YYYY-MM-DD
    GET /api/sales/reports/z-report/?date=YYYY-MM-DD

NOTE:
- Public storefront endpoints are mounted at /api/public/ via backend/urls.py
  and must NOT be included here.
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter

from sales.api.viewsets.sale import SaleViewSet
from sales.views.sale import CheckoutSaleView

# ✅ FIX: import from sales.api.pos_reports (no sales.api.views package needed)
from sales.api.pos_reports import (
    DailySalesReportView,
    CashReconciliationReportView,
    ZReportView,
)

router = DefaultRouter()

# ✅ Canonical staff endpoints
router.register(r"sales", SaleViewSet, basename="sales")

# ✅ Legacy alias so frontend calling /api/sales/ still works
router.register(r"", SaleViewSet, basename="sales-legacy-root")

urlpatterns = [
    # ✅ IMPORTANT: put explicit routes BEFORE router URLs
    path("checkout/", CheckoutSaleView.as_view(), name="sales-checkout"),

    # ✅ POS Reports (Admin-only)
    path("reports/daily/", DailySalesReportView.as_view(), name="sales-reports-daily"),
    path("reports/cash-recon/", CashReconciliationReportView.as_view(), name="sales-reports-cash-recon"),
    path("reports/z-report/", ZReportView.as_view(), name="sales-reports-z-report"),

    # ✅ Router endpoints
    path("", include(router.urls)),
]
