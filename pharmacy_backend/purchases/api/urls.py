# purchases/api/urls.py

from django.urls import path

from purchases.api.views import (
    PurchaseInvoiceListCreateView,
    PurchaseInvoiceReceiveView,
    SupplierListCreateView,
    SupplierPaymentListCreateView,
)

urlpatterns = [
    path("suppliers/", SupplierListCreateView.as_view(), name="purchase-suppliers"),
    path(
        "invoices/", PurchaseInvoiceListCreateView.as_view(), name="purchase-invoices"
    ),
    path(
        "invoices/<uuid:invoice_id>/receive/",
        PurchaseInvoiceReceiveView.as_view(),
        name="purchase-invoice-receive",
    ),
    path(
        "payments/", SupplierPaymentListCreateView.as_view(), name="supplier-payments"
    ),
]
