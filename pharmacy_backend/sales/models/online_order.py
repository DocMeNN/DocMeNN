# sales/models/online_order.py

import uuid
from decimal import Decimal

from django.db import models
from django.utils import timezone

from store.models import Store


class OnlineOrder(models.Model):
    """
    Public online store order (pre-Sale).

    Key rule:
    - OnlineOrder is created first (PENDING_PAYMENT)
    - It becomes PAID only after webhook verification
    - Only then do we convert to immutable Sale + deduct FIFO + post ledger
    """

    STATUS_PENDING_PAYMENT = "pending_payment"
    STATUS_PAID = "paid"
    STATUS_FULFILLED = "fulfilled"
    STATUS_CANCELLED = "cancelled"
    STATUS_EXPIRED = "expired"

    STATUS_CHOICES = [
        (STATUS_PENDING_PAYMENT, "Pending Payment"),
        (STATUS_PAID, "Paid"),
        (STATUS_FULFILLED, "Fulfilled"),
        (STATUS_CANCELLED, "Cancelled"),
        (STATUS_EXPIRED, "Expired"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    store = models.ForeignKey(
        Store,
        on_delete=models.PROTECT,
        related_name="online_orders",
    )

    order_no = models.CharField(
        max_length=64,
        unique=True,
        blank=True,
        help_text="System-generated public order number",
    )

    # Customer info (optional)
    customer_name = models.CharField(max_length=120, blank=True, default="")
    customer_phone = models.CharField(max_length=40, blank=True, default="")
    customer_email = models.EmailField(blank=True, default="")

    # Money fields (server authoritative)
    subtotal_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    tax_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    discount_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    total_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )

    status = models.CharField(
        max_length=32, choices=STATUS_CHOICES, default=STATUS_PENDING_PAYMENT
    )

    # Link to final Sale (after payment verification)
    sale = models.OneToOneField(
        "sales.Sale",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="source_online_order",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    fulfilled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["created_at"]),
            models.Index(fields=["status"]),
            models.Index(fields=["order_no"]),
            models.Index(fields=["store", "created_at"]),
            models.Index(fields=["store", "status"]),
        ]

    def save(self, *args, **kwargs):
        if not self.order_no:
            prefix = timezone.now().strftime("ORD%Y%m%d")
            self.order_no = f"{prefix}-{uuid.uuid4().hex[:8].upper()}"

        # If status flips to PAID and paid_at not set, stamp it
        if self.status == self.STATUS_PAID and not self.paid_at:
            self.paid_at = timezone.now()

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.order_no} | {self.total_amount} | {self.status}"
