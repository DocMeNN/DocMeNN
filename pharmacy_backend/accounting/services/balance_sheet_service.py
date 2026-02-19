# accounting/services/balance_sheet_service.py

"""
BALANCE SHEET SERVICE

Pure accounting read service.

Responsibilities:
- Compute balances per account as at a given date
- Classify balances into Assets, Liabilities, Equity
- Enforce accounting correctness (Assets = Liabilities + Equity)

Important:
- Revenue/Expense activity (if not closed) is represented as
  "Current Period Earnings" in Equity to keep the balance sheet correct.

Contract:
- API emits numeric JSON values (not strings)
- Provide both major-unit numbers (floats, 2dp) and minor-unit ints (exact)
- Provide liabilities_plus_equity in totals for frontend convenience

Critical accounting rules enforced here:
- Ledger truth is POSTED journal entries only
- Accounting timeline uses JournalEntry.posted_at (not LedgerEntry.created_at)
- Chart-aware + active accounts only
"""

from __future__ import annotations

from datetime import date as date_cls, datetime, time
from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Q, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from accounting.models.account import Account
from accounting.models.chart import ChartOfAccounts
from accounting.models.ledger import LedgerEntry
from accounting.services.account_resolver import get_active_chart
from accounting.services.exceptions import AccountingServiceError

TWOPLACES = Decimal("0.01")


def _q2(amount: Decimal) -> Decimal:
    return (amount or Decimal("0.00")).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def _to_major_number(amount: Decimal) -> float:
    return float(_q2(amount))


def _to_minor_int(amount: Decimal) -> int:
    return int((_q2(amount) * 100).to_integral_value(rounding=ROUND_HALF_UP))


def _parse_as_of_date(as_of_date: str | None) -> date_cls | None:
    if not as_of_date:
        return None
    try:
        return date_cls.fromisoformat(str(as_of_date).strip())
    except ValueError as exc:
        raise AccountingServiceError("Invalid as_of_date format (YYYY-MM-DD)") from exc


def _end_of_day_aware(d: date_cls) -> datetime:
    # Inclusive end-of-day snapshot
    naive = datetime.combine(d, time.max.replace(microsecond=0))
    if timezone.is_naive(naive):
        return timezone.make_aware(naive, timezone.get_current_timezone())
    return naive


def generate_balance_sheet(
    *, chart: ChartOfAccounts | None = None, as_of_date: str | None = None
) -> dict:
    """
    Args:
        chart: Optional ChartOfAccounts. Defaults to active chart.
        as_of_date: Optional YYYY-MM-DD string (inclusive end-of-day snapshot)

    Returns:
        {
            "assets": [{"code","name","balance","balance_minor"}...],
            "liabilities": [...],
            "equity": [...],
            "totals": {
                "assets": 0.0,
                "liabilities": 0.0,
                "equity": 0.0,
                "liabilities_plus_equity": 0.0,

                "assets_minor": 0,
                "liabilities_minor": 0,
                "equity_minor": 0,
                "liabilities_plus_equity_minor": 0,

                "balanced": true
            }
        }
    """
    active_chart = chart or get_active_chart()

    cutoff_d = _parse_as_of_date(as_of_date)
    cutoff_dt = _end_of_day_aware(cutoff_d) if cutoff_d else None

    relevant_types = (
        Account.ASSET,
        Account.LIABILITY,
        Account.EQUITY,
        Account.REVENUE,
        Account.EXPENSE,
    )

    accounts = list(
        Account.objects.filter(
            chart=active_chart,
            is_active=True,
            account_type__in=relevant_types,
        ).only("id", "code", "name", "account_type")
    )

    # Deterministic ordering for UI
    accounts.sort(key=lambda a: (a.account_type, a.code))

    account_ids = [a.id for a in accounts]
    if not account_ids:
        return {
            "assets": [],
            "liabilities": [],
            "equity": [],
            "totals": {
                "assets": 0.0,
                "liabilities": 0.0,
                "equity": 0.0,
                "liabilities_plus_equity": 0.0,
                "assets_minor": 0,
                "liabilities_minor": 0,
                "equity_minor": 0,
                "liabilities_plus_equity_minor": 0,
                "balanced": True,
            },
        }

    ledger_q = Q(
        account_id__in=account_ids,
        journal_entry__is_posted=True,
    )
    if cutoff_dt is not None:
        ledger_q &= Q(journal_entry__posted_at__lte=cutoff_dt)

    rows = (
        LedgerEntry.objects.filter(ledger_q)
        .values("account_id", "entry_type")
        .annotate(total=Coalesce(Sum("amount"), Decimal("0.00")))
    )

    debits = {acc_id: Decimal("0.00") for acc_id in account_ids}
    credits = {acc_id: Decimal("0.00") for acc_id in account_ids}

    for row in rows:
        acc_id = row["account_id"]
        amt = _q2(row["total"] or Decimal("0.00"))
        if row["entry_type"] == LedgerEntry.DEBIT:
            debits[acc_id] = amt
        elif row["entry_type"] == LedgerEntry.CREDIT:
            credits[acc_id] = amt

    def account_balance(acc: Account) -> Decimal:
        d = debits.get(acc.id, Decimal("0.00"))
        c = credits.get(acc.id, Decimal("0.00"))
        if acc.account_type in (Account.ASSET, Account.EXPENSE):
            return _q2(d - c)
        return _q2(c - d)

    sections = {"assets": [], "liabilities": [], "equity": []}
    totals = {
        "assets": Decimal("0.00"),
        "liabilities": Decimal("0.00"),
        "equity": Decimal("0.00"),
    }

    revenue_total = Decimal("0.00")
    expense_total = Decimal("0.00")

    for acc in accounts:
        bal = account_balance(acc)
        if bal == Decimal("0.00"):
            continue

        if acc.account_type == Account.REVENUE:
            revenue_total += bal
            continue

        if acc.account_type == Account.EXPENSE:
            expense_total += bal
            continue

        entry = {
            "code": acc.code,
            "name": acc.name,
            "balance": _to_major_number(bal),
            "balance_minor": _to_minor_int(bal),
        }

        if acc.account_type == Account.ASSET:
            sections["assets"].append(entry)
            totals["assets"] += bal
        elif acc.account_type == Account.LIABILITY:
            sections["liabilities"].append(entry)
            totals["liabilities"] += bal
        elif acc.account_type == Account.EQUITY:
            sections["equity"].append(entry)
            totals["equity"] += bal

    current_earnings = _q2(revenue_total - expense_total)
    if current_earnings != Decimal("0.00"):
        sections["equity"].append(
            {
                "code": "E-CURR",
                "name": "Current Period Earnings",
                "balance": _to_major_number(current_earnings),
                "balance_minor": _to_minor_int(current_earnings),
            }
        )
        totals["equity"] += current_earnings

    assets_q = _q2(totals["assets"])
    liabilities_plus_equity_q = _q2(totals["liabilities"] + totals["equity"])

    balanced = _to_minor_int(assets_q) == _to_minor_int(liabilities_plus_equity_q)
    if not balanced:
        raise AccountingServiceError(
            "Balance Sheet is unbalanced "
            f"(Assets={assets_q} Liabilities+Equity={liabilities_plus_equity_q})"
        )

    return {
        **sections,
        "totals": {
            "assets": _to_major_number(totals["assets"]),
            "liabilities": _to_major_number(totals["liabilities"]),
            "equity": _to_major_number(totals["equity"]),
            "liabilities_plus_equity": _to_major_number(liabilities_plus_equity_q),
            "assets_minor": _to_minor_int(totals["assets"]),
            "liabilities_minor": _to_minor_int(totals["liabilities"]),
            "equity_minor": _to_minor_int(totals["equity"]),
            "liabilities_plus_equity_minor": _to_minor_int(liabilities_plus_equity_q),
            "balanced": balanced,
        },
    }
