# accounting/models/period_close.py

"""
======================================================
PATH: accounting/models/period_close.py
======================================================
PERIOD CLOSE MODEL

Represents a locked accounting period close event.

Audit guarantees:
- Immutable once created
- Non-deletable
- Records the journal entry that executed the close

Hard rules:
- A chart cannot have overlapping closed periods.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q

from accounting.models.chart import ChartOfAccounts
from accounting.models.journal import JournalEntry


class PeriodClose(models.Model):
    chart = models.ForeignKey(
        ChartOfAccounts,
        on_delete=models.PROTECT,
        related_name="period_closes",
    )

    start_date = models.DateField()
    end_date = models.DateField()

    journal_entry = models.ForeignKey(
        JournalEntry,
        on_delete=models.PROTECT,
        related_name="period_closes",
        help_text="The journal entry that performed the close (Revenue/Expense -> Equity).",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-end_date", "-created_at"]
        indexes = [
            models.Index(fields=["chart", "start_date", "end_date"]),
            models.Index(fields=["end_date"]),
            models.Index(fields=["created_at"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["chart", "start_date", "end_date"],
                name="uniq_period_close_chart_start_end",
            ),
            models.CheckConstraint(
                condition=Q(end_date__gte=F("start_date")),
                name="chk_period_close_end_gte_start",
            ),
        ]
        verbose_name = "Period Close"
        verbose_name_plural = "Period Closes"

    def __str__(self):
        chart_name = getattr(self.chart, "name", "Chart")
        return f"PeriodClose {self.start_date} → {self.end_date} ({chart_name})"

    def clean(self):
        # Basic date sanity
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError({"end_date": "end_date must be >= start_date"})

        # Journal entry must be posted
        if self.journal_entry_id:
            # Accessing self.journal_entry is fine here (FK required)
            if not getattr(self.journal_entry, "is_posted", True):
                raise ValidationError({"journal_entry": "journal_entry must be posted"})

        # Prevent overlapping closes for the same chart
        if self.chart_id and self.start_date and self.end_date:
            qs = PeriodClose.objects.filter(chart_id=self.chart_id).filter(
                start_date__lte=self.end_date,
                end_date__gte=self.start_date,
            )
            if self.pk:
                qs = qs.exclude(pk=self.pk)

            if qs.exists():
                raise ValidationError(
                    {
                        "start_date": "This period overlaps an existing closed period for this chart.",
                        "end_date": "This period overlaps an existing closed period for this chart.",
                    }
                )

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("PeriodClose records are immutable once created")

        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("PeriodClose records are immutable and cannot be deleted")
