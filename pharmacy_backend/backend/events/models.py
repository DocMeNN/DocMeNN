"""
PATH: backend/events/models.py

EVENT OUTBOX MODEL

Stores domain events before they are dispatched.

Purpose:
- prevent event loss
- enable retries
- enable async workers
"""

from __future__ import annotations

import uuid

from django.db import models


class EventOutbox(models.Model):
    """
    Durable storage for domain events before they are dispatched
    to handlers or external workers.

    The outbox pattern guarantees:
    - no event loss
    - retry capability
    - async processing
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    event_type = models.CharField(
        max_length=255,
        help_text="Fully-qualified event name (e.g. inventory.stock_adjusted)",
    )

    payload = models.JSONField(
        help_text="Serialized event payload",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    processed = models.BooleanField(
        default=False,
        help_text="Whether the event has been dispatched",
    )

    processed_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    class Meta:
        db_table = "event_outbox"
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["processed"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.event_type} ({self.id})"