# accounting/models/account.py

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from accounting.models.chart import ChartOfAccounts


class Account(models.Model):
    """
    Represents a single account within a Chart of Accounts.

    Guarantees:
    - Account codes are unique per chart
    - Code + name are normalized (trimmed)
    - Chart-scoped integrity support for resolvers + reporting
    """

    ASSET = "ASSET"
    LIABILITY = "LIABILITY"
    EQUITY = "EQUITY"
    REVENUE = "REVENUE"
    EXPENSE = "EXPENSE"

    ACCOUNT_TYPES = [
        (ASSET, "Asset"),
        (LIABILITY, "Liability"),
        (EQUITY, "Equity"),
        (REVENUE, "Revenue"),
        (EXPENSE, "Expense"),
    ]

    chart = models.ForeignKey(
        ChartOfAccounts,
        on_delete=models.PROTECT,
        related_name="accounts",
    )

    code = models.CharField(max_length=10)
    name = models.CharField(max_length=150)

    account_type = models.CharField(
        max_length=20,
        choices=ACCOUNT_TYPES,
    )

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["code"]
        verbose_name = "Account"
        verbose_name_plural = "Accounts"
        indexes = [
            models.Index(fields=["chart", "code"]),
            models.Index(fields=["chart", "account_type"]),
            models.Index(fields=["is_active"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["chart", "code"],
                name="uniq_account_chart_code",
            ),
            models.CheckConstraint(
                condition=~Q(code=""),
                name="chk_account_code_not_blank",
            ),
            models.CheckConstraint(
                condition=~Q(name=""),
                name="chk_account_name_not_blank",
            ),
        ]

    def __str__(self):
        return f"{self.code} – {self.name}"

    def clean(self):
        self.code = (self.code or "").strip()
        self.name = (self.name or "").strip()

        if not self.code:
            raise ValidationError("Account code is required")
        if not self.name:
            raise ValidationError("Account name is required")

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)
