# accounting/services/trial_balance_service.py

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Sum
from django.utils import timezone
from django.utils.timezone import now

from accounting.models.ledger import LedgerEntry
from accounting.models.account import Account
from accounting.services.account_resolver import get_active_chart


TWOPLACES = Decimal("0.01")


def _q2(amount: Decimal) -> Decimal:
    return (amount or Decimal("0.00")).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def _to_major_number(amount: Decimal) -> float:
    return float(_q2(amount))


def _to_minor_int(amount: Decimal) -> int:
    return int((_q2(amount) * 100).to_integral_value(rounding=ROUND_HALF_UP))


def _as_aware_dt(dt):
    if dt is None:
        return None
    if timezone.is_naive(dt):
        return timezone.make_aware(dt, timezone.get_current_timezone())
    return dt


class TrialBalanceService:
    """
    Trial Balance computation service.

    Guarantees:
    - Scopes to provided chart OR ACTIVE chart
    - Scopes to ACTIVE accounts only
    - Uses POSTED journal_entry.posted_at as accounting timeline
    - Avoids N+1 queries by aggregating in bulk
    - Returns JSON-safe numeric values (no Decimals)
    """

    def __init__(self, account_model=Account, ledger_model=LedgerEntry):
        self.Account = account_model
        self.Ledger = ledger_model

    def generate(self, *, chart=None, as_of=None):
        cutoff = _as_aware_dt(as_of) or now()
        active_chart = chart or get_active_chart()

        accounts = list(
            self.Account.objects.filter(chart=active_chart, is_active=True)
            .only("id", "code", "name")
            .order_by("code")
        )

        if not accounts:
            return {
                "as_of": cutoff.isoformat(),
                "accounts": [],
                "totals": {
                    "debit": 0.0,
                    "credit": 0.0,
                    "debit_minor": 0,
                    "credit_minor": 0,
                    "balanced": True,
                },
            }

        account_ids = [a.id for a in accounts]

        rows = (
            self.Ledger.objects.filter(
                account_id__in=account_ids,
                journal_entry__is_posted=True,
                journal_entry__posted_at__lte=cutoff,
            )
            .values("account_id", "entry_type")
            .annotate(total=Sum("amount"))
        )

        debit_by_account = {acc_id: Decimal("0.00") for acc_id in account_ids}
        credit_by_account = {acc_id: Decimal("0.00") for acc_id in account_ids}

        for r in rows:
            acc_id = r["account_id"]
            total = _q2(r["total"] or Decimal("0.00"))

            if r["entry_type"] == self.Ledger.DEBIT:
                debit_by_account[acc_id] = total
            elif r["entry_type"] == self.Ledger.CREDIT:
                credit_by_account[acc_id] = total

        accounts_output = []
        total_debit = Decimal("0.00")
        total_credit = Decimal("0.00")

        for acc in accounts:
            debit = _q2(debit_by_account.get(acc.id, Decimal("0.00")))
            credit = _q2(credit_by_account.get(acc.id, Decimal("0.00")))

            if debit == Decimal("0.00") and credit == Decimal("0.00"):
                continue

            accounts_output.append(
                {
                    "account_id": acc.id,
                    "account_code": acc.code,
                    "account_name": acc.name,
                    "debit": _to_major_number(debit),
                    "credit": _to_major_number(credit),
                    "debit_minor": _to_minor_int(debit),
                    "credit_minor": _to_minor_int(credit),
                }
            )

            total_debit += debit
            total_credit += credit

        total_debit = _q2(total_debit)
        total_credit = _q2(total_credit)

        balanced = _to_minor_int(total_debit) == _to_minor_int(total_credit)

        return {
            "as_of": cutoff.isoformat(),
            "accounts": accounts_output,
            "totals": {
                "debit": _to_major_number(total_debit),
                "credit": _to_major_number(total_credit),
                "debit_minor": _to_minor_int(total_debit),
                "credit_minor": _to_minor_int(total_credit),
                "balanced": balanced,
            },
        }
