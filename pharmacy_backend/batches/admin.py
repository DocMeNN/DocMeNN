from django.contrib import admin

from batches.models import Batch, StockMovement


@admin.register(Batch)
class BatchAdmin(admin.ModelAdmin):
    list_display = ("product", "batch_number", "expiry_date", "quantity")
    list_filter = ("expiry_date",)
    search_fields = ("batch_number", "product__name")


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ("batch", "movement_type", "quantity", "created_at")
    list_filter = ("movement_type",)
