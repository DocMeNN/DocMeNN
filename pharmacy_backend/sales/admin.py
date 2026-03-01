# sales/admin.py

from django.contrib import admin
from sales.models.sale import Sale
from sales.models.refund_audit import SaleRefundAudit


# ======================================================
# SALE ADMIN
# ======================================================


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = (
        "invoice_no",
        "status",
        "total_amount",
        "total_refunded_amount",
        "remaining_refundable_amount",
        "created_at",
    )
    readonly_fields = (
        "invoice_no",
        "total_refunded_amount",
        "remaining_refundable_amount",
        "created_at",
        "completed_at",
    )
    search_fields = ("invoice_no",)
    list_filter = ("status", "created_at")


# ======================================================
# REFUND AUDIT ADMIN
# ======================================================


@admin.register(SaleRefundAudit)
class SaleRefundAuditAdmin(admin.ModelAdmin):
    list_display = (
        "sale",
        "total_amount",
        "refunded_by",
        "refunded_at",
        "is_accounted",
    )
    readonly_fields = (
        "sale",
        "subtotal_amount",
        "tax_amount",
        "discount_amount",
        "total_amount",
        "cogs_amount",
        "gross_profit_amount",
        "refunded_by",
        "refunded_at",
        "is_accounted",
    )
    search_fields = ("sale__invoice_no",)
    list_filter = ("refunded_at", "is_accounted")