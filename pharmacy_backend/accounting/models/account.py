# accounting/models/account.py

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from accounting.models.chart import ChartOfAccounts


class Account(models.Model):
    """
    Represents a single account within a Chart of Accounts.

    Enterprise Guarantees:
    - Account codes are unique per chart
    - Chart-scoped integrity
    - Hierarchical accounts supported (parent → children)
    - Control accounts protected from manual posting
    - System accounts protected from deletion
    - Normal balance stored for accounting validation
    """

    ASSET = "ASSET"
    LIABILITY = "LIABILITY"
    EQUITY = "EQUITY"
    REVENUE = "REVENUE"
    EXPENSE = "EXPENSE"
    COGS = "COGS"

    ACCOUNT_TYPES = [
        (ASSET, "Asset"),
        (LIABILITY, "Liability"),
        (EQUITY, "Equity"),
        (REVENUE, "Revenue"),
        (EXPENSE, "Expense"),
        (COGS, "Cost of Goods Sold"),
    ]

    NORMAL_BALANCES = [
        ("DEBIT", "Debit"),
        ("CREDIT", "Credit"),
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

    normal_balance = models.CharField(
        max_length=6,
        choices=NORMAL_BALANCES,
        default="DEBIT",
        help_text="Expected accounting balance direction",
    )

    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="children",
    )

    description = models.TextField(blank=True)

    is_active = models.BooleanField(default=True)

    system_account = models.BooleanField(
        default=False,
        help_text="System accounts cannot be deleted or modified",
    )

    is_control_account = models.BooleanField(
        default=False,
        help_text="Control accounts cannot receive manual journal postings",
    )

    allow_manual_posting = models.BooleanField(
        default=True,
        help_text="If False, only system modules may post here",
    )

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

        if self.parent and self.parent.chart_id != self.chart_id:
            raise ValidationError("Parent account must belong to the same chart")

    def save(self, *args, **kwargs):
        if self.pk and self.system_account:
            raise ValidationError("System accounts cannot be modified")

        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.system_account:
            raise ValidationError("System accounts cannot be deleted")
        return super().delete(*args, **kwargs)