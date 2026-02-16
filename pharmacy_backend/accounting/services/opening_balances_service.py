# PATH: accounting/services/opening_balances_service.py

"""
OPENING BALANCES SERVICE

Responsibilities:
- Validate + normalize payload using domain rules
- Resolve account codes -> Account objects in ACTIVE chart
- Build postings and call posting engine (create_journal_entry)
- Atomic + idempotent via reference_type/reference_id constraint

No HTTP, no DRF serializers here.
"""

from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from typing import Iterable, Optional

from django.db import transaction
from django.utils import timezone

from accounting.models.account import Account
from accounting.opening_balance import (
    OpeningBalanceError,
    OpeningBalancePayload,
    build_opening_balance_reference_id,
)
from accounting.services.account_resolver import get_active_chart
from accounting.services.exceptions import (
    AccountResolutionError,
    IdempotencyError,
    JournalEntryCreationError,
)
from accounting.services.journal_entry_service import create_journal_entry


class OpeningBalancesError(ValueError):
    """Raised when opening balances payload is invalid or cannot be posted."""


def _end_of_day_aware(d: date) -> datetime:
    naive = datetime.combine(d, time(23, 59, 59))
    if timezone.is_naive(naive):
        return timezone.make_aware(naive, timezone.get_current_timezone())
    return naive


@transaction.atomic
def create_opening_balances(
    *,
    business_id: str,
    as_of_date: date,
    raw_lines: Iterable[dict],
    chart_id: Optional[str] = None,
):
    """
    Create opening balances (idempotent).

    raw_lines format:
      [{"account_code": "1000", "dc": "D", "amount": 500000}, ...]

    Idempotency:
      reference_type="OPENING_BALANCE"
      reference_id="<business_id>:<chart_id>:<as_of_date>"
    """
    try:
        payload = OpeningBalancePayload.from_raw(
            business_id=business_id,
            as_of_date=as_of_date,
            raw_lines=raw_lines,
        )
    except OpeningBalanceError as exc:
        raise OpeningBalancesError(str(exc)) from exc

    chart = get_active_chart()
    active_chart_id = str(chart.id)

    if chart_id is None:
        chart_id = active_chart_id
    else:
        if str(chart_id).strip() != active_chart_id:
            raise OpeningBalancesError(
                f"chart_id does not match active chart. Passed={chart_id} Active={active_chart_id}"
            )

    codes = [l.account_code for l in payload.lines]
    accounts = Account.objects.filter(chart=chart, is_active=True, code__in=codes)
    accounts_by_code = {a.code: a for a in accounts}

    missing = [c for c in codes if c not in accounts_by_code]
    if missing:
        raise AccountResolutionError(
            f"Some account codes were not found in active chart ({getattr(chart, 'name', 'ACTIVE_CHART')}): {missing}"
        )

    postings = []
    for line in payload.lines:
        account = accounts_by_code[line.account_code]
        if line.dc == "D":
            postings.append({"account": account, "debit": line.amount, "credit": Decimal("0.00")})
        else:
            postings.append({"account": account, "debit": Decimal("0.00"), "credit": line.amount})

    posted_at_dt = _end_of_day_aware(payload.as_of_date)
    reference_id = build_opening_balance_reference_id(
        business_id=payload.business_id,
        chart_id=chart_id,
        as_of_date=payload.as_of_date,
    )

    try:
        return create_journal_entry(
            description=f"Opening Balances as at {payload.as_of_date.isoformat()}",
            postings=postings,
            reference_type="OPENING_BALANCE",
            reference_id=reference_id,
            posted_at=posted_at_dt,
        )
    except IdempotencyError as exc:
        transaction.set_rollback(True)
        raise OpeningBalancesError(str(exc)) from exc
    except (JournalEntryCreationError, AccountResolutionError) as exc:
        transaction.set_rollback(True)
        raise OpeningBalancesError(str(exc)) from exc
    except Exception as exc:
        transaction.set_rollback(True)
        raise OpeningBalancesError(f"Failed to post opening balances: {exc}") from exc
