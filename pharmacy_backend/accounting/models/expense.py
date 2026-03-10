# accounting/models/expense.py

from __future__ import annotations

import uuid
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone

from accounting.models.account import Account
from accounting.models.journal import JournalEntry
from store.models import Store

User = settings.AUTH_USER_MODEL


class Expense(models.Model):
    """
    Expense transaction (business event), posted to the ledger via the engine.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    PAYMENT_CASH = "cash"
    PAYMENT_BANK = "bank"
    PAYMENT_CREDIT = "credit"

    PAYMENT_METHODS = [
        (PAYMENT_CASH, "Cash"),
        (PAYMENT_BANK, "Bank"),
        (PAYMENT_CREDIT, "Credit (Payables)"),
    ]

    store = models.ForeignKey(
        Store,
        on_delete=models.PROTECT,
        related_name="expenses",
        null=True,
        blank=True,
        db_index=True,
    )

    expense_date = models.DateField(default=timezone.localdate)

    amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )

    expense_account = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        related_name="expenses_as_category",
    )

    payment_method = models.CharField(
        max_length=10,
        choices=PAYMENT_METHODS,
        default=PAYMENT_CASH,
    )

    payment_account = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        related_name="expenses_as_payment",
    )

    vendor = models.CharField(max_length=150, blank=True, default="")
    narration = models.CharField(max_length=255, blank=True, default="")

    is_posted = models.BooleanField(default=False)

    posted_journal_entry = models.ForeignKey(
        JournalEntry,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="posted_expenses",
    )

    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_expenses",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-expense_date", "-created_at"]
        verbose_name = "Expense"
        verbose_name_plural = "Expenses"
        indexes = [
            models.Index(fields=["expense_date"]),
            models.Index(fields=["is_posted"]),
            models.Index(fields=["created_at"]),
            models.Index(fields=["store"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(is_posted=False, posted_journal_entry__isnull=True)
                | Q(is_posted=True, posted_journal_entry__isnull=False),
                name="chk_expense_posted_requires_journal",
            )
        ]

    def __str__(self):
        return f"Expense {self.id} - {self.amount} ({self.expense_date})"

    def clean(self):
        if self.expense_account_id and self.payment_account_id:
            if getattr(self.expense_account, "chart_id", None) != getattr(
                self.payment_account, "chart_id", None
            ):
                raise ValidationError(
                    "expense_account and payment_account must belong to the same chart."
                )

        if self.is_posted and self.posted_journal_entry_id is None:
            raise ValidationError(
                "posted_journal_entry is required when is_posted=True."
            )

        if not self.is_posted and self.posted_journal_entry_id is not None:
            raise ValidationError(
                "posted_journal_entry must be null when is_posted=False."
            )

    def save(self, *args, **kwargs):
        if self.pk and type(self).objects.filter(pk=self.pk, is_posted=True).exists():
            raise ValidationError("Expense records are immutable once posted")

        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.pk and type(self).objects.filter(pk=self.pk, is_posted=True).exists():
            raise ValidationError("Posted expense records cannot be deleted")

        return super().delete(*args, **kwargs)