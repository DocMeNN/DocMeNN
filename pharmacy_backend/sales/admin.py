from django.contrib import admin

from sales.models.sale import Sale
from sales.models.sale_item import SaleItem
from sales.models.refund_audit import SaleRefundAudit


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = (
        "invoice_no",
        "status",
        "total_amount",
        "created_at",
        "completed_at",
    )
    readonly_fields = [f.name for f in Sale._meta.fields]
    ordering = ("-created_at",)


@admin.register(SaleItem)
class SaleItemAdmin(admin.ModelAdmin):
    list_display = (
        "sale",
        "product",
        "quantity",
        "unit_price",
        "total_price",
    )
    readonly_fields = [f.name for f in SaleItem._meta.fields]


@admin.register(SaleRefundAudit)
class SaleRefundAuditAdmin(admin.ModelAdmin):
    list_display = (
        "sale",
        "refunded_by",
        "original_total_amount",
        "refunded_at",
    )
    readonly_fields = [f.name for f in SaleRefundAudit._meta.fields]
