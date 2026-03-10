# ============================================================
# PATH: accounting/models/event.py
# ============================================================

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

from store.models import Store

User = settings.AUTH_USER_MODEL


class AccountingEvent(models.Model):
    """
    Event log that represents a business event requiring accounting processing.

    This layer decouples operational modules (POS, refunds, inventory, etc.)
    from the accounting engine.

    Events are immutable once created and can be safely replayed to rebuild
    accounting history if needed.
    """

    EVENT_SALE_COMPLETED = "sale_completed"
    EVENT_REFUND_ISSUED = "refund_issued"
    EVENT_EXPENSE_RECORDED = "expense_recorded"
    EVENT_INVENTORY_ADJUSTMENT = "inventory_adjustment"

    EVENT_TYPES = [
        (EVENT_SALE_COMPLETED, "Sale Completed"),
        (EVENT_REFUND_ISSUED, "Refund Issued"),
        (EVENT_EXPENSE_RECORDED, "Expense Recorded"),
        (EVENT_INVENTORY_ADJUSTMENT, "Inventory Adjustment"),
    ]

    PROCESSING_PENDING = "pending"
    PROCESSING_PROCESSED = "processed"
    PROCESSING_FAILED = "failed"

    PROCESSING_STATUS = [
        (PROCESSING_PENDING, "Pending"),
        (PROCESSING_PROCESSED, "Processed"),
        (PROCESSING_FAILED, "Failed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # ============================================================
    # EVENT SOURCE
    # ============================================================

    event_type = models.CharField(
        max_length=50,
        choices=EVENT_TYPES,
        db_index=True,
    )

    source_model = models.CharField(
        max_length=100,
        help_text="Model name that generated the event (Sale, RefundAudit, Expense, etc.)",
    )

    source_id = models.UUIDField(
        help_text="Primary key of the originating object",
        db_index=True,
    )

    store = models.ForeignKey(
        Store,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="accounting_events",
        db_index=True,
    )

    # ============================================================
    # PROCESSING STATUS
    # ============================================================

    processing_status = models.CharField(
        max_length=20,
        choices=PROCESSING_STATUS,
        default=PROCESSING_PENDING,
        db_index=True,
    )

    processed_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    # ============================================================
    # AUDIT TRAIL
    # ============================================================

    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_accounting_events",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    error_message = models.TextField(
        blank=True,
        null=True,
        help_text="Processing error if event failed",
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["event_type"]),
            models.Index(fields=["processing_status"]),
            models.Index(fields=["source_model", "source_id"]),
            models.Index(fields=["store", "created_at"]),
        ]

    def __str__(self):
        return f"{self.event_type} | {self.source_model}:{self.source_id}"

    def mark_processed(self):
        self.processing_status = self.PROCESSING_PROCESSED
        self.processed_at = timezone.now()
        self.save(update_fields=["processing_status", "processed_at"])

    def mark_failed(self, message: str):
        self.processing_status = self.PROCESSING_FAILED
        self.error_message = message
        self.save(update_fields=["processing_status", "error_message"])