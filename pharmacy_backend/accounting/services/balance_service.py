# accounting/services/balance_service.py

"""
BALANCE & REPORTING SERVICE (AUTHORITATIVE)

Read-only ledger aggregation helpers.

RULES:
- READ-ONLY: no writes, ever
- LedgerEntry is the single source of truth
- Accounting timeline uses JournalEntry.posted_at (not LedgerEntry.created_at)
- Only POSTED journals count (journal_entry__is_posted=True)
- Chart-aware: never mix charts
"""

from __future__ import annotations

from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Case, F, Sum, When
from django.db.models.functions import Coalesce
from django.utils import timezone

from accounting.models.account import Account
from accounting.models.ledger import LedgerEntry


class BalanceServiceError(Exception):
    """Base error for balance and reporting services."""


TWOPLACES = Decimal("0.01")


def _q2(v) -> Decimal:
    return Decimal(str(v or "0.00")).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def _as_aware_dt(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if timezone.is_naive(dt):
        return timezone.make_aware(dt, timezone.get_current_timezone())
    return dt


def _ledger_qs_for_account(*, account: Account, as_of: datetime | None = None):
    qs = LedgerEntry.objects.filter(
        account=account,
        journal_entry__is_posted=True,
    ).select_related("journal_entry")

    as_of_dt = _as_aware_dt(as_of)
    if as_of_dt is not None:
        qs = qs.filter(journal_entry__posted_at__lte=as_of_dt)

    return qs


def _ledger_qs_for_chart(*, chart, as_of: datetime | None = None):
    qs = LedgerEntry.objects.filter(
        account__chart=chart,
        account__is_active=True,
        journal_entry__is_posted=True,
    ).select_related("journal_entry")

    as_of_dt = _as_aware_dt(as_of)
    if as_of_dt is not None:
        qs = qs.filter(journal_entry__posted_at__lte=as_of_dt)

    return qs


def get_account_balance(account: Account, *, as_of: datetime | None = None) -> Decimal:
    """
    Balance rule:
    - Assets & Expenses → Debit balance  (debits - credits)
    - Liabilities, Equity & Revenue → Credit balance (credits - debits)
    """
    if account is None:
        raise BalanceServiceError("Account is required")

    aggregates = _ledger_qs_for_account(account=account, as_of=as_of).aggregate(
        debit_total=Coalesce(
            Sum(Case(When(entry_type=LedgerEntry.DEBIT, then=F("amount")))),
            Decimal("0.00"),
        ),
        credit_total=Coalesce(
            Sum(Case(When(entry_type=LedgerEntry.CREDIT, then=F("amount")))),
            Decimal("0.00"),
        ),
    )

    debit = _q2(aggregates["debit_total"])
    credit = _q2(aggregates["credit_total"])

    if account.account_type in (Account.ASSET, Account.EXPENSE):
        return _q2(debit - credit)

    return _q2(credit - debit)


def get_trial_balance(chart, *, as_of: datetime | None = None) -> list[dict]:
    """
    Bulk trial balance (no N+1). Uses posted_at for time filtering.
    """
    if chart is None:
        raise BalanceServiceError("Chart of Accounts is required")

    accounts = list(
        Account.objects.filter(chart=chart, is_active=True)
        .only("id", "code", "name", "account_type")
        .order_by("code")
    )

    if not accounts:
        return []

    account_ids = [a.id for a in accounts]

    qs = _ledger_qs_for_chart(chart=chart, as_of=as_of).filter(
        account_id__in=account_ids
    )

    rows = qs.values("account_id", "entry_type").annotate(
        total=Coalesce(Sum("amount"), Decimal("0.00"))
    )

    debit_by = {acc_id: Decimal("0.00") for acc_id in account_ids}
    credit_by = {acc_id: Decimal("0.00") for acc_id in account_ids}

    for r in rows:
        acc_id = r["account_id"]
        total = _q2(r["total"])
        if r["entry_type"] == LedgerEntry.DEBIT:
            debit_by[acc_id] = total
        elif r["entry_type"] == LedgerEntry.CREDIT:
            credit_by[acc_id] = total

    results = []
    for acc in accounts:
        debit = _q2(debit_by.get(acc.id))
        credit = _q2(credit_by.get(acc.id))

        if acc.account_type in (Account.ASSET, Account.EXPENSE):
            bal = _q2(debit - credit)
        else:
            bal = _q2(credit - debit)

        results.append(
            {
                "account_id": acc.id,
                "code": acc.code,
                "name": acc.name,
                "account_type": acc.account_type,
                "debit_total": debit,
                "credit_total": credit,
                "balance": bal,
            }
        )

    return results


def get_totals_by_account_type(*, chart, as_of: datetime | None = None) -> dict:
    if chart is None:
        raise BalanceServiceError("Chart is required")

    totals = {
        Account.ASSET: Decimal("0.00"),
        Account.LIABILITY: Decimal("0.00"),
        Account.EQUITY: Decimal("0.00"),
        Account.REVENUE: Decimal("0.00"),
        Account.EXPENSE: Decimal("0.00"),
    }

    tb = get_trial_balance(chart, as_of=as_of)

    for row in tb:
        totals[row["account_type"]] = _q2(totals[row["account_type"]] + row["balance"])

    return totals


def get_profit_and_loss(chart, *, as_of: datetime | None = None) -> dict:
    totals = get_totals_by_account_type(chart=chart, as_of=as_of)

    revenue = _q2(totals[Account.REVENUE])
    expenses = _q2(totals[Account.EXPENSE])

    return {
        "revenue": revenue,
        "expenses": expenses,
        "net_profit": _q2(revenue - expenses),
    }
