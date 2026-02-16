# accounting/services/profit_and_loss_service.py

"""
PROFIT & LOSS SERVICE (INCOME STATEMENT)

Read-only aggregation over immutable ledger entries.

Contract-locked numbers:
{
  "income": float,
  "expenses": float,
  "net_profit": float,
  "income_minor": int,
  "expenses_minor": int,
  "net_profit_minor": int
}

Key rules:
- Uses JournalEntry.posted_at as the accounting effective date
- Scopes to ACTIVE accounts in the selected chart
"""

from __future__ import annotations

from datetime import datetime, date
from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Sum, Q
from django.utils import timezone

from accounting.models.ledger import LedgerEntry
from accounting.models.account import Account


TWOPLACES = Decimal("0.01")


def _q2(amount: Decimal) -> Decimal:
    return (amount or Decimal("0.00")).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def _to_major_number(amount: Decimal) -> float:
    return float(_q2(amount))


def _to_minor_int(amount: Decimal) -> int:
    return int((_q2(amount) * 100).to_integral_value(rounding=ROUND_HALF_UP))


def _as_aware_dt(v):
    if v is None:
        return None

    if isinstance(v, date) and not isinstance(v, datetime):
        v = datetime.combine(v, datetime.max.time().replace(microsecond=0))

    if isinstance(v, datetime):
        if timezone.is_naive(v):
            return timezone.make_aware(v, timezone.get_current_timezone())
        return v

    return v


def get_profit_and_loss(*, chart=None, start_date=None, end_date=None):
    start_dt = _as_aware_dt(start_date)
    end_dt = _as_aware_dt(end_date)

    qs = (
        LedgerEntry.objects
        .select_related("account", "journal_entry")
        .filter(
            journal_entry__is_posted=True,
            account__is_active=True,
        )
    )

    if chart is not None:
        qs = qs.filter(account__chart=chart)

    if start_dt:
        qs = qs.filter(journal_entry__posted_at__gte=start_dt)

    if end_dt:
        qs = qs.filter(journal_entry__posted_at__lte=end_dt)

    income_totals = qs.filter(
        account__account_type=Account.REVENUE
    ).aggregate(
        credits=Sum("amount", filter=Q(entry_type=LedgerEntry.CREDIT)),
        debits=Sum("amount", filter=Q(entry_type=LedgerEntry.DEBIT)),
    )

    total_income = _q2(income_totals["credits"]) - _q2(income_totals["debits"])

    expense_totals = qs.filter(
        account__account_type=Account.EXPENSE
    ).aggregate(
        debits=Sum("amount", filter=Q(entry_type=LedgerEntry.DEBIT)),
        credits=Sum("amount", filter=Q(entry_type=LedgerEntry.CREDIT)),
    )

    total_expenses = _q2(expense_totals["debits"]) - _q2(expense_totals["credits"])

    net_profit = _q2(total_income - total_expenses)

    return {
        "income": _to_major_number(total_income),
        "expenses": _to_major_number(total_expenses),
        "net_profit": _to_major_number(net_profit),
        "income_minor": _to_minor_int(total_income),
        "expenses_minor": _to_minor_int(total_expenses),
        "net_profit_minor": _to_minor_int(net_profit),
    }
