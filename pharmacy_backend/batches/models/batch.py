# batches/models/batch.py

from django.db import models
from django.utils import timezone


class Batch(models.Model):
    """
    LEGACY MODEL (PHASE 2)

    This batch model overlaps with `products.StockBatch` (canonical).

    Canonical batch model:
      - products.models.StockBatch

    This remains for compatibility, but new inventory logic should use
    `products.StockBatch` + `products.StockMovement`.

    Important Fix:
    - Product FK must point to the actual Product model you use: `products.Product`
      (NOT `store.Product`).
    """

    product = models.ForeignKey(
        "products.Product",
        on_delete=models.CASCADE,
        related_name="legacy_batches",
    )

    batch_number = models.CharField(max_length=100)
    expiry_date = models.DateField()

    # Legacy quantity (single field)
    quantity = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["expiry_date"]
        unique_together = ("product", "batch_number")
        indexes = [
            models.Index(fields=["expiry_date"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        product_name = getattr(self.product, "name", "Product")
        return f"{product_name} | {self.batch_number}"

    @property
    def is_expired(self) -> bool:
        return self.expiry_date < timezone.now().date()

    @property
    def is_out_of_stock(self) -> bool:
        return self.quantity <= 0
