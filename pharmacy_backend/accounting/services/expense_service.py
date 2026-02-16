# PATH: accounting/services/expense_service.py

"""
EXPENSE POSTING SERVICE

Responsibilities:
- Validate expense payload
- Resolve accounts in active chart
- Create Expense business record
- Post immutable JournalEntry (atomic + idempotent)
- Enforce period correctness via posted_at handling

Security (Phase 5):
- Posting expenses requires explicit permission:
    accounting.add_expense
  (staff flag alone is NOT enough)

Accounting Effect:
- Dr Expense Account
- Cr Cash / Bank / Accounts Payable
"""

from __future__ import annotations

from datetime import date as date_type, datetime, time
from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from accounting.models.account import Account
from accounting.models.expense import Expense
from accounting.services.account_resolver import (
    get_active_chart,
    get_cash_account,
    get_bank_account,
    get_accounts_payable_account,
)
from accounting.services.posting import post_expense_to_ledger
from accounting.services.exceptions import (
    AccountResolutionError,
    JournalEntryCreationError,
    IdempotencyError,
)

TWOPLACES = Decimal("0.01")
EXPENSE_POST_PERMISSION = "accounting.add_expense"


class ExpensePostingError(ValueError):
    pass


class ExpensePermissionError(ExpensePostingError):
    pass


def _money(v) -> Decimal:
    return Decimal(str(v or "0.00")).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def _normalize_expense_date(expense_date) -> date_type:
    if expense_date is None:
        return timezone.localdate()
    if isinstance(expense_date, date_type):
        return expense_date
    raise ExpensePostingError("expense_date must be a date")


def _end_of_day_aware(d: date_type) -> datetime:
    naive = datetime.combine(d, time(23, 59, 59))
    if timezone.is_naive(naive):
        return timezone.make_aware(naive, timezone.get_current_timezone())
    return naive


def _resolve_account_by_code(*, code: str) -> Account:
    chart = get_active_chart()
    code = (code or "").strip()
    if not code:
        raise ExpensePostingError("Account code is required")

    try:
        return Account.objects.get(chart=chart, code=code, is_active=True)
    except Account.DoesNotExist as exc:
        raise AccountResolutionError(
            f"Account with code={code} not found in active chart ({getattr(chart, 'name', 'ACTIVE_CHART')})."
        ) from exc
    except Account.MultipleObjectsReturned as exc:
        raise AccountResolutionError(
            f"Multiple active accounts found with code={code} in active chart ({getattr(chart, 'name', 'ACTIVE_CHART')})."
        ) from exc


def _resolve_payment_account(*, payment_method: str, payable_account_code: str | None) -> Account:
    method = (payment_method or Expense.PAYMENT_CASH).lower().strip()

    if method == Expense.PAYMENT_CASH:
        return get_cash_account()

    if method == Expense.PAYMENT_BANK:
        return get_bank_account()

    if method == Expense.PAYMENT_CREDIT:
        code = (payable_account_code or "").strip()
        return _resolve_account_by_code(code=code) if code else get_accounts_payable_account()

    raise ExpensePostingError("Invalid payment_method. Use 'cash', 'bank', or 'credit'.")


def _ensure_same_chart(*, expense_account: Account, payment_account: Account) -> None:
    if expense_account.chart_id != payment_account.chart_id:
        raise ExpensePostingError("expense_account and payment_account must belong to the same active chart.")


def _assert_can_post_expense(*, user) -> None:
    if user is None:
        raise ExpensePermissionError("You do not have permission to post expenses.")

    try:
        allowed = bool(user.has_perm(EXPENSE_POST_PERMISSION))
    except Exception:
        allowed = False

    if not allowed:
        raise ExpensePermissionError("You do not have permission to post expenses.")


@transaction.atomic
def create_expense_and_post(
    *,
    user,
    expense_date,
    amount,
    expense_account_code: str,
    payment_method: str,
    payable_account_code: str | None = None,
    vendor: str = "",
    narration: str = "",
) -> Expense:
    _assert_can_post_expense(user=user)

    amt = _money(amount)
    if amt <= Decimal("0.00"):
        raise ExpensePostingError("Amount must be > 0")

    expense_date = _normalize_expense_date(expense_date)

    expense_account = _resolve_account_by_code(code=expense_account_code)
    payment_account = _resolve_payment_account(
        payment_method=payment_method,
        payable_account_code=payable_account_code,
    )
    _ensure_same_chart(expense_account=expense_account, payment_account=payment_account)

    expense = Expense.objects.create(
        expense_date=expense_date,
        amount=amt,
        expense_account=expense_account,
        payment_method=payment_method,
        payment_account=payment_account,
        vendor=(vendor or "").strip(),
        narration=(narration or "").strip(),
        is_posted=False,
        posted_journal_entry=None,
    )

    try:
        je = post_expense_to_ledger(
            expense_id=str(expense.id),
            expense_date=_end_of_day_aware(expense.expense_date),
            narration=expense.narration or expense.vendor or "Expense",
            expense_account=expense.expense_account,
            payment_account=expense.payment_account,
            amount=expense.amount,
        )
    except (IdempotencyError, JournalEntryCreationError) as exc:
        transaction.set_rollback(True)
        raise ExpensePostingError(str(exc)) from exc
    except Exception as exc:
        transaction.set_rollback(True)
        raise ExpensePostingError(f"Failed to post expense: {exc}") from exc

    expense.is_posted = True
    expense.posted_journal_entry = je

    try:
        expense.full_clean()
    except ValidationError as exc:
        transaction.set_rollback(True)
        raise ExpensePostingError(str(exc)) from exc

    expense.save(update_fields=["is_posted", "posted_journal_entry"])
    return expense
