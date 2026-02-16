# accounting/services/overview_service.py

"""
ACCOUNTING OVERVIEW KPI SERVICE

Ledger-driven KPI aggregation for dashboards.

Contract:
- Returns numeric JSON-safe values (floats for major units + ints for minor units)
- null only used when a value is truly not computable (we mostly return 0.0 instead)
- Read-only: no mutations, no postings.
"""

from decimal import Decimal, ROUND_HALF_UP
from datetime import date
from django.db.models import Sum, Q

from accounting.models.account import Account
from accounting.models.ledger import LedgerEntry
from accounting.services.exceptions import AccountingServiceError


TWOPLACES = Decimal("0.01")


def _q2(amount: Decimal) -> Decimal:
    return (amount or Decimal("0.00")).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def _to_major_number(amount: Decimal) -> float:
    return float(_q2(amount))


def _to_minor_int(amount: Decimal) -> int:
    return int((_q2(amount) * 100).to_integral_value(rounding=ROUND_HALF_UP))


def _parse_as_of_date(as_of_date: str | None) -> date | None:
    if not as_of_date:
        return None
    try:
        return date.fromisoformat(as_of_date)
    except ValueError:
        raise AccountingServiceError("Invalid as_of_date format (YYYY-MM-DD)")


def get_accounting_overview_kpis(
    *,
    as_of_date: str | None = None,
    start_date=None,
    end_date=None,
) -> dict:
    """
    Returns KPI snapshot using the ledger.

    - Balance sheet KPIs are computed "as of" as_of_date (YYYY-MM-DD).
    - P&L KPIs are computed for [start_date, end_date] if provided.

    Output:
    {
      "as_of_date": "YYYY-MM-DD" | null,
      "period": {"start_date": "...", "end_date": "..."},
      "assets": number, "liabilities": number, "equity": number,
      "revenue": number, "expenses": number, "net_profit": number,
      "assets_minor": int, ... etc
    }
    """

    cutoff = _parse_as_of_date(as_of_date)

    # -------------------------
    # BALANCE SHEET TOTALS (AS-OF)
    # -------------------------
    bs_filter = Q()
    if cutoff:
        bs_filter &= Q(created_at__date__lte=cutoff)

    relevant_types = (
        Account.ASSET,
        Account.LIABILITY,
        Account.EQUITY,
        Account.REVENUE,
        Account.EXPENSE,
    )

    accounts = list(
        Account.objects.filter(is_active=True, account_type__in=relevant_types)
        .only("id", "account_type")
    )
    account_type_by_id = {a.id: a.account_type for a in accounts}
    account_ids = list(account_type_by_id.keys())

    # Aggregate ledger totals once
    rows = (
        LedgerEntry.objects.filter(bs_filter, account_id__in=account_ids)
        .values("account_id", "entry_type")
        .annotate(total=Sum("amount"))
    )

    debits = {acc_id: Decimal("0.00") for acc_id in account_ids}
    credits = {acc_id: Decimal("0.00") for acc_id in account_ids}

    for r in rows:
        acc_id = r["account_id"]
        amt = _q2(r["total"] or Decimal("0.00"))
        if r["entry_type"] == LedgerEntry.DEBIT:
            debits[acc_id] = amt
        elif r["entry_type"] == LedgerEntry.CREDIT:
            credits[acc_id] = amt

    assets = Decimal("0.00")
    liabilities = Decimal("0.00")
    equity = Decimal("0.00")

    # We include current earnings in equity (pre-closing)
    revenue_asof = Decimal("0.00")
    expenses_asof = Decimal("0.00")

    for acc_id, acc_type in account_type_by_id.items():
        d = debits.get(acc_id, Decimal("0.00"))
        c = credits.get(acc_id, Decimal("0.00"))

        if acc_type in (Account.ASSET, Account.EXPENSE):
            bal = _q2(d - c)
        else:
            bal = _q2(c - d)

        if bal == Decimal("0.00"):
            continue

        if acc_type == Account.ASSET:
            assets += bal
        elif acc_type == Account.LIABILITY:
            liabilities += bal
        elif acc_type == Account.EQUITY:
            equity += bal
        elif acc_type == Account.REVENUE:
            revenue_asof += bal
        elif acc_type == Account.EXPENSE:
            expenses_asof += bal

    current_earnings_asof = _q2(revenue_asof - expenses_asof)
    equity_with_earnings = _q2(equity + current_earnings_asof)

    # -------------------------
    # PROFIT & LOSS TOTALS (PERIOD)
    # -------------------------
    pl_filter = Q()
    if start_date:
        pl_filter &= Q(created_at__gte=start_date)
    if end_date:
        pl_filter &= Q(created_at__lte=end_date)

    income_totals = (
        LedgerEntry.objects.filter(pl_filter, account__account_type=Account.REVENUE)
        .aggregate(
            credits=Sum("amount", filter=Q(entry_type=LedgerEntry.CREDIT)),
            debits=Sum("amount", filter=Q(entry_type=LedgerEntry.DEBIT)),
        )
    )

    revenue_period = _q2((income_totals["credits"] or Decimal("0.00"))) - _q2(
        (income_totals["debits"] or Decimal("0.00"))
    )

    expense_totals = (
        LedgerEntry.objects.filter(pl_filter, account__account_type=Account.EXPENSE)
        .aggregate(
            debits=Sum("amount", filter=Q(entry_type=LedgerEntry.DEBIT)),
            credits=Sum("amount", filter=Q(entry_type=LedgerEntry.CREDIT)),
        )
    )

    expenses_period = _q2((expense_totals["debits"] or Decimal("0.00"))) - _q2(
        (expense_totals["credits"] or Decimal("0.00"))
    )

    net_profit_period = _q2(revenue_period - expenses_period)

    return {
        "as_of_date": str(cutoff) if cutoff else None,
        "period": {
            "start_date": start_date.isoformat() if start_date else None,
            "end_date": end_date.isoformat() if end_date else None,
        },
        "assets": _to_major_number(assets),
        "liabilities": _to_major_number(liabilities),
        "equity": _to_major_number(equity_with_earnings),
        "revenue": _to_major_number(revenue_period),
        "expenses": _to_major_number(expenses_period),
        "net_profit": _to_major_number(net_profit_period),
        "assets_minor": _to_minor_int(assets),
        "liabilities_minor": _to_minor_int(liabilities),
        "equity_minor": _to_minor_int(equity_with_earnings),
        "revenue_minor": _to_minor_int(revenue_period),
        "expenses_minor": _to_minor_int(expenses_period),
        "net_profit_minor": _to_minor_int(net_profit_period),
    }
