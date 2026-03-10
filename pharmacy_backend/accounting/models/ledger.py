# accounting/models/ledger.py

from __future__ import annotations

import uuid
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models

from accounting.models.account import Account
from accounting.models.journal import JournalEntry


class LedgerEntry(models.Model):
    """
    Immutable debit/credit line belonging to a JournalEntry.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    DEBIT = "DEBIT"
    CREDIT = "CREDIT"

    ENTRY_TYPES = [
        (DEBIT, "Debit"),
        (CREDIT, "Credit"),
    ]

    journal_entry = models.ForeignKey(
        JournalEntry,
        on_delete=models.PROTECT,
        related_name="ledger_entries",
    )

    account = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        related_name="ledger_entries",
    )

    entry_type = models.CharField(
        max_length=6,
        choices=ENTRY_TYPES,
    )

    amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
        help_text="Positive monetary value",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Ledger Entry"
        verbose_name_plural = "Ledger Entries"
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["account"]),
            models.Index(fields=["journal_entry"]),
            models.Index(fields=["entry_type"]),
            models.Index(fields=["created_at"]),
            models.Index(fields=["account", "entry_type"]),
            models.Index(fields=["journal_entry", "entry_type"]),
        ]

    def __str__(self):
        return f"{self.entry_type} {self.amount} → {self.account}"

    def clean(self):
        if self.entry_type not in (self.DEBIT, self.CREDIT):
            raise ValidationError("Invalid entry_type")

        if self.journal_entry_id and not getattr(self.journal_entry, "is_posted", True):
            raise ValidationError(
                "Ledger entries can only reference posted journal entries"
            )

        if self.amount is None or self.amount <= 0:
            raise ValidationError("Ledger amount must be > 0")

        if (
            self.account
            and self.account.is_control_account
            and self.account.allow_manual_posting
        ):
            raise ValidationError(
                "Control accounts cannot receive manual ledger postings"
            )

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError(
                "LedgerEntry records are immutable and cannot be modified"
            )

        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("LedgerEntry records are immutable and cannot be deleted")