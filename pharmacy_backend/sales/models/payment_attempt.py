# sales/models/payment_attempt.py

import uuid
from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


class PaymentAttempt(models.Model):
    """
    Payment attempt for an OnlineOrder.

    Idempotency rule:
    - reference is unique (Paystack reference)
    - webhook processing must be idempotent using this reference (and/or event id if available)
    """

    PROVIDER_PAYSTACK = "paystack"
    PROVIDER_CHOICES = [
        (PROVIDER_PAYSTACK, "Paystack"),
    ]

    STATUS_INITIATED = "initiated"
    STATUS_REDIRECTED = "redirected"
    STATUS_VERIFIED = "verified"
    STATUS_FAILED = "failed"
    STATUS_EXPIRED = "expired"

    STATUS_CHOICES = [
        (STATUS_INITIATED, "Initiated"),
        (STATUS_REDIRECTED, "Redirected"),
        (STATUS_VERIFIED, "Verified"),
        (STATUS_FAILED, "Failed"),
        (STATUS_EXPIRED, "Expired"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    order = models.ForeignKey(
        "sales.OnlineOrder",
        on_delete=models.CASCADE,
        related_name="payment_attempts",
    )

    provider = models.CharField(max_length=32, choices=PROVIDER_CHOICES, default=PROVIDER_PAYSTACK)

    reference = models.CharField(
        max_length=128,
        unique=True,
        help_text="Provider reference (Paystack reference). Must be unique for idempotency.",
    )

    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    currency = models.CharField(max_length=8, default="NGN")

    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default=STATUS_INITIATED)

    authorization_url = models.URLField(blank=True, default="")
    provider_payload = models.JSONField(default=dict, blank=True)

    initiated_at = models.DateTimeField(auto_now_add=True)
    verified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-initiated_at"]
        indexes = [
            models.Index(fields=["initiated_at"]),
            models.Index(fields=["status"]),
            models.Index(fields=["provider"]),
            models.Index(fields=["reference"]),
            models.Index(fields=["order", "initiated_at"]),
        ]

    def mark_verified(self, payload=None):
        self.status = self.STATUS_VERIFIED
        self.verified_at = self.verified_at or timezone.now()
        if payload is not None:
            self.provider_payload = payload

    def __str__(self):
        return f"{self.provider}:{self.reference} | {self.status}"