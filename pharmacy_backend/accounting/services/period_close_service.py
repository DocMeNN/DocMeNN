# PATH: accounting/services/period_close_service.py

"""
PERIOD CLOSE SERVICE

Closes an accounting period by zeroing out:
- Revenue accounts
- Expense accounts

…into a Retained Earnings (Equity) account, by creating ONE journal entry.

Guarantees:
- Atomic: journal entry + PeriodClose record created together
- Idempotent: reference_type="PERIOD_CLOSE", reference_id="<chart_id>:<start>:<end>"
- Prevents overlapping closes for the chart
- Posts at end-of-day for end_date
"""

from __future__ import annotations

from datetime import datetime, time
from decimal import ROUND_HALF_UP, Decimal

from django.db import IntegrityError, transaction
from django.db.models import Case, F, Sum, When
from django.db.models.functions import Coalesce
from django.utils import timezone

from accounting.models.account import Account
from accounting.models.ledger import LedgerEntry
from accounting.models.period_close import PeriodClose
from accounting.services.account_resolver import get_active_chart
from accounting.services.exceptions import (
    AccountResolutionError,
    IdempotencyError,
    JournalEntryCreationError,
)
from accounting.services.journal_entry_service import create_journal_entry

TWOPLACES = Decimal("0.01")


class PeriodCloseError(ValueError):
    pass


def _money(v) -> Decimal:
    return Decimal(str(v or "0.00")).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def _resolve_account_by_code(*, chart, code: str) -> Account:
    code = (code or "").strip()
    if not code:
        raise PeriodCloseError("Account code is required")

    try:
        return Account.objects.get(chart=chart, code=code, is_active=True)
    except Account.DoesNotExist as exc:
        raise AccountResolutionError(
            f"Account with code={code} not found in active chart ({getattr(chart, 'name', 'ACTIVE_CHART')})."
        ) from exc
    except Account.MultipleObjectsReturned as exc:
        raise AccountResolutionError(
            f"Multiple active accounts found with code={code} in active chart ({getattr(chart, 'name', 'ACTIVE_CHART')}). "
            "Account codes must be unique per chart."
        ) from exc


def _resolve_retained_earnings_account(*, chart, override_code: str | None) -> Account:
    code = (override_code or "").strip()
    if code:
        return _resolve_account_by_code(chart=chart, code=code)

    try:
        return _resolve_account_by_code(chart=chart, code="3100")
    except AccountResolutionError:
        pass

    retained = (
        Account.objects.filter(
            chart=chart,
            is_active=True,
            account_type=Account.EQUITY,
            name__icontains="retained",
        )
        .order_by("code")
        .first()
    )
    if retained:
        return retained

    fallback = (
        Account.objects.filter(
            chart=chart,
            is_active=True,
            account_type=Account.EQUITY,
        )
        .order_by("code")
        .first()
    )
    if fallback:
        return fallback

    raise PeriodCloseError(
        "No EQUITY account found in active chart to receive retained earnings. "
        "Create an equity account (e.g., Retained Earnings) or pass retained_earnings_account_code."
    )


def _validate_period_dates(*, start_date, end_date) -> None:
    if not start_date or not end_date:
        raise PeriodCloseError("start_date and end_date are required")
    if start_date > end_date:
        raise PeriodCloseError("start_date cannot be after end_date")

    today = timezone.localdate()
    if end_date > today:
        raise PeriodCloseError(
            f"Cannot close a future period. end_date={end_date} today={today}"
        )


def _ensure_no_overlap(*, chart, start_date, end_date) -> None:
    overlaps = PeriodClose.objects.filter(
        chart=chart,
        start_date__lte=end_date,
        end_date__gte=start_date,
    ).exists()
    if overlaps:
        raise PeriodCloseError(
            "This period overlaps an already-closed period for the active chart. Choose a non-overlapping range."
        )


def _end_of_day_dt(d) -> datetime:
    naive = datetime.combine(d, time(23, 59, 59))
    if timezone.is_naive(naive):
        return timezone.make_aware(naive, timezone.get_current_timezone())
    return naive


@transaction.atomic
def close_period(
    *,
    start_date,
    end_date,
    retained_earnings_account_code: str | None = None,
):
    """
    CLOSE PERIOD (Revenue/Expense -> Retained Earnings)

    Idempotency:
      reference_type="PERIOD_CLOSE"
      reference_id="<chart_id>:<start>:<end>"
    """
    _validate_period_dates(start_date=start_date, end_date=end_date)

    chart = get_active_chart()

    if PeriodClose.objects.filter(
        chart=chart, start_date=start_date, end_date=end_date
    ).exists():
        raise PeriodCloseError(
            "This period has already been closed for the active chart"
        )

    _ensure_no_overlap(chart=chart, start_date=start_date, end_date=end_date)

    retained_earnings = _resolve_retained_earnings_account(
        chart=chart,
        override_code=retained_earnings_account_code,
    )

    base_qs = LedgerEntry.objects.select_related("account", "journal_entry").filter(
        account__chart=chart,
        account__is_active=True,
        journal_entry__is_posted=True,
        journal_entry__posted_at__date__gte=start_date,
        journal_entry__posted_at__date__lte=end_date,
        account__account_type__in=[Account.REVENUE, Account.EXPENSE],
    )

    if not base_qs.exists():
        raise PeriodCloseError("No revenue/expense activity found in this period")

    per_account = base_qs.values("account_id", "account__account_type").annotate(
        debit_total=Coalesce(
            Sum(Case(When(entry_type=LedgerEntry.DEBIT, then=F("amount")))),
            Decimal("0.00"),
        ),
        credit_total=Coalesce(
            Sum(Case(When(entry_type=LedgerEntry.CREDIT, then=F("amount")))),
            Decimal("0.00"),
        ),
    )

    account_ids = [row["account_id"] for row in per_account]
    accounts_by_id = {
        a.id: a
        for a in Account.objects.filter(id__in=account_ids, chart=chart, is_active=True)
    }

    postings = []
    total_revenue = Decimal("0.00")
    total_expenses = Decimal("0.00")

    for row in per_account:
        acc_id = row["account_id"]
        acc_type = row["account__account_type"]
        debit = _money(row["debit_total"])
        credit = _money(row["credit_total"])

        account = accounts_by_id.get(acc_id)
        if not account:
            raise PeriodCloseError(
                f"Account id={acc_id} referenced in ledger is not active in current chart. Resolve chart consistency."
            )

        # Revenue normally has credit balances; we DEBIT to zero it out.
        if acc_type == Account.REVENUE:
            net = (credit - debit).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
            if net > 0:
                postings.append(
                    {"account": account, "debit": net, "credit": Decimal("0.00")}
                )
                total_revenue += net

        # Expense normally has debit balances; we CREDIT to zero it out.
        elif acc_type == Account.EXPENSE:
            net = (debit - credit).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
            if net > 0:
                postings.append(
                    {"account": account, "debit": Decimal("0.00"), "credit": net}
                )
                total_expenses += net

    total_revenue = total_revenue.quantize(TWOPLACES, rounding=ROUND_HALF_UP)
    total_expenses = total_expenses.quantize(TWOPLACES, rounding=ROUND_HALF_UP)
    net_profit = (total_revenue - total_expenses).quantize(
        TWOPLACES, rounding=ROUND_HALF_UP
    )

    if total_revenue == Decimal("0.00") and total_expenses == Decimal("0.00"):
        raise PeriodCloseError("Nothing to close: period revenue and expenses are zero")

    # Post net to retained earnings (profit => credit equity, loss => debit equity)
    if net_profit > Decimal("0.00"):
        postings.append(
            {
                "account": retained_earnings,
                "debit": Decimal("0.00"),
                "credit": net_profit,
            }
        )
    elif net_profit < Decimal("0.00"):
        postings.append(
            {
                "account": retained_earnings,
                "debit": abs(net_profit),
                "credit": Decimal("0.00"),
            }
        )

    ref_id = f"{chart.id}:{start_date.isoformat()}:{end_date.isoformat()}"
    description = f"Period Close {start_date.isoformat()} → {end_date.isoformat()}"
    posted_at_dt = _end_of_day_dt(end_date)

    try:
        journal_entry = create_journal_entry(
            description=description,
            postings=postings,
            reference_type="PERIOD_CLOSE",
            reference_id=ref_id,
            posted_at=posted_at_dt,
        )
    except (IdempotencyError, JournalEntryCreationError) as exc:
        raise PeriodCloseError(str(exc)) from exc
    except Exception as exc:
        raise PeriodCloseError(f"Failed to close period: {exc}") from exc

    # Race-safe create
    try:
        PeriodClose.objects.create(
            chart=chart,
            start_date=start_date,
            end_date=end_date,
            journal_entry=journal_entry,
        )
    except IntegrityError as exc:
        raise PeriodCloseError(
            "Failed to create PeriodClose record (possible overlap/duplicate under concurrency)."
        ) from exc

    return {
        "journal_entry": journal_entry,
        "total_revenue": total_revenue,
        "total_expenses": total_expenses,
        "net_profit": net_profit,
    }
