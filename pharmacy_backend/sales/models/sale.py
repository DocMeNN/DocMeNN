# ============================================================
# PATH: sales/models/sale.py
# ============================================================

import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Sum
from django.utils import timezone

from store.models import Store
from accounting.models.event import AccountingEvent

User = settings.AUTH_USER_MODEL


class Sale(models.Model):
    STATUS_DRAFT = "draft"
    STATUS_COMPLETED = "completed"
    STATUS_REFUNDED = "refunded"

    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_REFUNDED, "Refunded"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # ============================================================
    # MULTI-RETAIL FOUNDATION
    # ============================================================

    store = models.ForeignKey(
        Store,
        on_delete=models.PROTECT,
        related_name="sales",
        db_index=True,
        null=True,
        blank=True,
    )

    invoice_no = models.CharField(max_length=64, unique=True, blank=True)

    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="sales",
    )

    subtotal_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    tax_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    discount_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    total_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    cogs_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    gross_profit_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    payment_method = models.CharField(
        max_length=32,
        default="cash",
    )

    status = models.CharField(
        max_length=32,
        choices=STATUS_CHOICES,
        default=STATUS_COMPLETED,
    )

    created_at = models.DateTimeField(auto_now_add=True)

    completed_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["store", "created_at"]),
            models.Index(fields=["status"]),
        ]

    # ============================================================
    # REFUND AGGREGATES
    # ============================================================

    @property
    def total_refunded_amount(self):
        return (
            self.refund_audits.aggregate(total=Sum("total_amount"))["total"]
            or Decimal("0.00")
        )

    @property
    def remaining_refundable_amount(self):
        return Decimal(self.total_amount) - Decimal(self.total_refunded_amount)

    # ============================================================
    # ACCOUNTING EVENT CREATION
    # ============================================================

    def create_accounting_event(self):
        """
        Creates accounting event for completed sale if not already created.
        """

        existing_event = AccountingEvent.objects.filter(
            event_type=AccountingEvent.EVENT_SALE_COMPLETED,
            source_model="Sale",
            source_id=self.id,
        ).exists()

        if existing_event:
            return

        AccountingEvent.objects.create(
            event_type=AccountingEvent.EVENT_SALE_COMPLETED,
            source_model="Sale",
            source_id=self.id,
            store=self.store,
            created_by=self.user,
        )

    # ============================================================

    def save(self, *args, **kwargs):
        is_new = self._state.adding

        if not self.invoice_no:
            prefix = timezone.now().strftime("INV%Y%m%d")
            self.invoice_no = f"{prefix}-{uuid.uuid4().hex[:8].upper()}"

        if self.status == self.STATUS_COMPLETED and not self.completed_at:
            self.completed_at = timezone.now()

        try:
            self.gross_profit_amount = Decimal(self.subtotal_amount) - Decimal(
                self.cogs_amount
            )
        except Exception:
            pass

        super().save(*args, **kwargs)

        # ========================================================
        # EVENT GENERATION
        # ========================================================

        if self.status == self.STATUS_COMPLETED:
            self.create_accounting_event()

    def __str__(self):
        store_name = getattr(self.store, "name", "Store")
        return f"{store_name} | {self.invoice_no} | {self.total_amount}"