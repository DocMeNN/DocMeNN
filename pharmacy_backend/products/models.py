# pharmacy_backend/products/models.py

import uuid
from django.db import models
from django.db.models import Sum
from django.conf import settings


# ==================== CATEGORY ====================

class Category(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "Categories"

    def __str__(self):
        return self.name


# ==================== PRODUCT ====================

class Product(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="products",
    )

    sku = models.CharField(max_length=128, unique=True, db_index=True)
    name = models.CharField(max_length=255, db_index=True)

    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    low_stock_threshold = models.PositiveIntegerField(default=10)

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} ({self.sku})"

    @property
    def total_stock(self):
        return (
            self.stock_batches
            .filter(is_active=True)
            .aggregate(total=Sum("quantity_remaining"))
            .get("total")
            or 0
        )

    @property
    def is_low_stock(self):
        return self.total_stock <= self.low_stock_threshold


# ==================== STOCK BATCH (FIFO SOURCE) ====================

class StockBatch(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="stock_batches",
    )

    batch_number = models.CharField(max_length=128)
    expiry_date = models.DateField()

    quantity_received = models.PositiveIntegerField()
    quantity_remaining = models.PositiveIntegerField()

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["expiry_date", "created_at"]  # FIFO
        constraints = [
            models.UniqueConstraint(
                fields=["product", "batch_number"],
                name="unique_batch_per_product",
            )
        ]

    def save(self, *args, **kwargs):
        if self.quantity_remaining <= 0:
            self.quantity_remaining = 0
            self.is_active = False
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.product.name} | Batch {self.batch_number}"


# ==================== STOCK MOVEMENT AUDIT (LEDGER) ====================

class StockMovement(models.Model):
    """
    Immutable audit log of ALL stock movements.
    """

    class MovementType(models.TextChoices):
        IN = "IN", "Stock In"
        OUT = "OUT", "Stock Out"

    class Reason(models.TextChoices):
        SALE = "SALE", "Sale"
        RECEIPT = "RECEIPT", "Stock Receipt"
        ADJUSTMENT = "ADJUSTMENT", "Manual Adjustment"
        EXPIRY = "EXPIRY", "Expired Stock"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="stock_movements",
    )

    batch = models.ForeignKey(
        StockBatch,
        on_delete=models.CASCADE,
        related_name="stock_movements",
    )

    movement_type = models.CharField(
        max_length=3,
        choices=MovementType.choices,
    )

    reason = models.CharField(
        max_length=20,
        choices=Reason.choices,
    )

    quantity = models.PositiveIntegerField(
        help_text="Always positive. Direction defined by movement_type."
    )

    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stock_movements",
    )

    # ✅ SAFE FK TO SALE
    sale = models.ForeignKey(
        "sales.Sale",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stock_movements",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["created_at"]),
            models.Index(fields=["movement_type"]),
            models.Index(fields=["reason"]),
            models.Index(fields=["sale"]),
        ]

    def __str__(self):
        return f"{self.product.name} | {self.reason} | {self.quantity}"
