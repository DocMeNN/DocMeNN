# sales/models/sale_payment_allocation.py

import uuid
from decimal import Decimal

from django.db import models


class SalePaymentAllocation(models.Model):
    """
    Immutable payment legs for a Sale.

    RULES:
    - Sum(amount) must equal sale.total_amount (enforced in checkout orchestrator).
    - Allocations are write-once: created at checkout time.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    sale = models.ForeignKey(
        "sales.Sale",
        on_delete=models.PROTECT,
        related_name="payment_allocations",
    )

    METHOD_CASH = "cash"
    METHOD_BANK = "bank"
    METHOD_POS = "pos"
    METHOD_TRANSFER = "transfer"
    METHOD_CREDIT = "credit"

    METHOD_CHOICES = [
        (METHOD_CASH, "Cash"),
        (METHOD_BANK, "Bank"),
        (METHOD_POS, "POS"),
        (METHOD_TRANSFER, "Transfer"),
        (METHOD_CREDIT, "Credit"),
    ]

    method = models.CharField(max_length=32, choices=METHOD_CHOICES)
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))

    reference = models.CharField(max_length=128, blank=True, default="")
    note = models.CharField(max_length=255, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["sale"]),
            models.Index(fields=["method"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return f"{self.sale_id} | {self.method} | {self.amount}"
