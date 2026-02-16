# PATH: public/models.py

"""
PATH: public/models.py

PUBLIC APP MODELS (ONLINE STORE)

Phase 4 Goal:
Introduce an OnlineOrder that is payment-gateway safe.

Why we need this model:
- A Sale is an immutable accounting event (it should only exist AFTER payment is confirmed).
- Payment gateways are asynchronous (initiate now, confirm later via webhook).
- Therefore we need an Order record to hold:
  - pending intent (items/customer/store)
  - provider reference (Paystack reference)
  - status lifecycle (pending -> paid -> fulfilled / cancelled / expired)
  - link to final Sale once paid

Design principles:
- Store-scoped and audit-friendly.
- Status transitions are controlled (no silent rewrites).
- Minimal fields now; extend later (shipping, delivery, discounts, etc).
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from django.db import models
from django.utils import timezone


class OnlineOrder(models.Model):
    """
    Payment-gateway safe order record for the public online store.
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

    PROVIDER_PAYSTACK = "paystack"

    PROVIDER_CHOICES = [
        (PROVIDER_PAYSTACK, "Paystack"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    order_no = models.CharField(
        max_length=64,
        unique=True,
        blank=True,
        help_text="System-generated public order number",
    )

    # Store scope (we keep it loose: use store_id if Store model exists)
    store_id = models.UUIDField(db_index=True)

    status = models.CharField(
        max_length=32,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING_PAYMENT,
        db_index=True,
    )

    provider = models.CharField(
        max_length=32,
        choices=PROVIDER_CHOICES,
        default=PROVIDER_PAYSTACK,
        db_index=True,
    )

    currency = models.CharField(max_length=8, default="NGN")

    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Total payable amount for this order",
    )

    # Customer info (optional, but useful for receipts/support)
    customer_name = models.CharField(max_length=255, blank=True, default="")
    customer_phone = models.CharField(max_length=64, blank=True, default="")
    customer_email = models.EmailField(blank=True, default="")

    # Items snapshot (public cart is client-side, so we store a safe server snapshot here)
    # Format example:
    # [{"product_id": "...", "quantity": 2, "unit_price": "1500.00", "line_total": "3000.00"}]
    items_snapshot = models.JSONField(default=list, blank=True)

    # Paystack reference (unique per initiated payment)
    provider_reference = models.CharField(max_length=128, blank=True, default="", db_index=True)

    # When provider confirms payment
    paid_at = models.DateTimeField(null=True, blank=True)

    # Link to final Sale (once paid)
    sale_id = models.UUIDField(null=True, blank=True, db_index=True)

    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["store_id", "created_at"]),
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["provider", "provider_reference"]),
        ]

    def save(self, *args, **kwargs):
        if not self.order_no:
            prefix = timezone.now().strftime("ORD%Y%m%d")
            self.order_no = f"{prefix}-{uuid.uuid4().hex[:8].upper()}"
        super().save(*args, **kwargs)

    def mark_paid(self, *, reference: str | None = None, paid_at=None, sale_id=None):
        """
        Controlled transition into PAID.
        Keeps the model logic centralized (services should call this, not set fields directly).
        """
        if self.status not in (self.STATUS_PENDING_PAYMENT,):
            raise ValueError(f"Order cannot be marked paid from status '{self.status}'")

        self.status = self.STATUS_PAID
        if reference:
            self.provider_reference = reference
        self.paid_at = paid_at or timezone.now()
        if sale_id:
            self.sale_id = sale_id

    def mark_fulfilled(self):
        if self.status != self.STATUS_PAID:
            raise ValueError("Order can only be fulfilled after payment is confirmed (PAID).")
        self.status = self.STATUS_FULFILLED

    def cancel(self):
        if self.status in (self.STATUS_PAID, self.STATUS_FULFILLED):
            raise ValueError("Paid/fulfilled orders cannot be cancelled.")
        self.status = self.STATUS_CANCELLED

    def __str__(self):
        return f"{self.order_no} ({self.status})"