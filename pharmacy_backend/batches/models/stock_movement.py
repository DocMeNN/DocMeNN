# batches/models/stock_movement.py

from django.core.exceptions import ValidationError
from django.db import models


class StockMovement(models.Model):
    """
    LEGACY MODEL (PHASE 2)

    This app overlaps with the canonical inventory engine in `products`.

    Canonical inventory ledger:
      - products.models.StockMovement
      - products.models.StockBatch
      - products.services.inventory

    This model remains ONLY for backward compatibility with any old code paths.
    New code must NOT write here.
    """

    IN = "IN"
    OUT = "OUT"

    MOVEMENT_TYPE_CHOICES = [
        (IN, "Stock In"),
        (OUT, "Stock Out"),
    ]

    batch = models.ForeignKey(
        "batches.Batch", on_delete=models.CASCADE, related_name="movements"
    )

    movement_type = models.CharField(max_length=3, choices=MOVEMENT_TYPE_CHOICES)

    quantity = models.PositiveIntegerField()
    reason = models.CharField(max_length=255)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["created_at"]),
            models.Index(fields=["movement_type"]),
        ]

    def clean(self):
        if self.quantity <= 0:
            raise ValidationError("quantity must be greater than zero")

    def __str__(self):
        return f"{self.movement_type} | {self.quantity} | {self.batch}"
