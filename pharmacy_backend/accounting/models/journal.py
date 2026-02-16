# accounting/models/journal.py

"""
======================================================
PATH: accounting/models/journal.py
======================================================
JOURNAL ENTRY MODEL

Represents a single accounting transaction (journal header).

Guarantees:
- Immutable once created (no updates, no deletes)
- Idempotency via reference uniqueness (when reference is provided)
- posted_at is the accounting effective date (used for period locks and reports)
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone


class JournalEntry(models.Model):
    reference = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="External reference (POS sale ID, refund ID, etc.)",
    )

    description = models.TextField(help_text="Narrative description of the journal entry")

    posted_at = models.DateTimeField(
        default=timezone.now,
        help_text="Accounting effective date",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="Timestamp when the journal entry was created",
    )

    is_posted = models.BooleanField(
        default=True,
        help_text="Once posted, journal entries are immutable",
    )

    class Meta:
        ordering = ["-posted_at", "-created_at"]
        indexes = [
            models.Index(fields=["posted_at"]),
            models.Index(fields=["created_at"]),
            models.Index(fields=["reference"]),
            models.Index(fields=["is_posted"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["reference"],
                condition=Q(reference__isnull=False) & ~Q(reference=""),
                name="uniq_journal_reference_not_blank",
            )
        ]
        verbose_name = "Journal Entry"
        verbose_name_plural = "Journal Entries"

    def __str__(self):
        return f"JournalEntry #{self.id} – {self.posted_at.date()}"

    def clean(self):
        if self.reference is not None:
            ref = str(self.reference).strip()
            self.reference = ref or None

        self.description = (self.description or "").strip()
        if not self.description:
            raise ValidationError("Journal entry description is required")

        if self.posted_at and timezone.is_naive(self.posted_at):
            self.posted_at = timezone.make_aware(self.posted_at, timezone.get_current_timezone())

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("JournalEntry records are immutable once created")

        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("JournalEntry records are immutable and cannot be deleted")
