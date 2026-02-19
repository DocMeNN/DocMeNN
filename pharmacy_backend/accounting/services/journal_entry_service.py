# accounting/services/journal_entry_service.py

"""
======================================================
PATH: accounting/services/journal_entry_service.py
======================================================
JOURNAL ENTRY SERVICE (ACCOUNTING ENGINE)

This module is the ONLY place allowed to:
- Create JournalEntry
- Create LedgerEntry
- Enforce debit == credit
- Guarantee atomicity
- Enforce idempotency via reference (prevents double-posting)
- Enforce period locks (no posting into closed periods)

Everything else (POS, refunds, adjustments) must pass through here.

ANTI-CIRCULAR-IMPORT RULE:
- Do NOT import period_lock at module import time.
- Import it lazily inside the enforcement function.
"""

from __future__ import annotations

from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django.db import IntegrityError, transaction
from django.utils import timezone

from accounting.models.journal import JournalEntry
from accounting.models.ledger import LedgerEntry
from accounting.services.exceptions import (
    IdempotencyError,
    JournalEntryCreationError,
)

TWOPLACES = Decimal("0.01")
MIN_LINE_AMOUNT = Decimal("0.01")


def _money(value) -> Decimal:
    if value is None or value == "":
        return Decimal("0.00")

    if isinstance(value, Decimal):
        amt = value
    else:
        try:
            amt = Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError) as exc:
            raise JournalEntryCreationError(f"Invalid money value: {value!r}") from exc

    return amt.quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def _as_aware_dt(dt: datetime | None) -> datetime:
    if dt is None:
        return timezone.now()
    if timezone.is_naive(dt):
        return timezone.make_aware(dt, timezone.get_current_timezone())
    return dt


def _normalize_reference(
    reference_type: str | None, reference_id: str | None
) -> str | None:
    if not reference_type or not reference_id:
        return None

    rt = str(reference_type).strip()
    rid = str(reference_id).strip()
    if not rt or not rid:
        return None

    ref = f"{rt}:{rid}"
    if ref.startswith(":") or ref.endswith(":"):
        raise JournalEntryCreationError("Invalid reference_type/reference_id")

    return ref


def _infer_chart_from_postings(normalized_postings: list[dict]) -> object:
    first_account = normalized_postings[0]["account"]
    chart = getattr(first_account, "chart", None)
    if chart is None:
        raise JournalEntryCreationError("Posting accounts must belong to a chart")

    for line in normalized_postings[1:]:
        acc = line["account"]
        if getattr(acc, "chart_id", None) != getattr(chart, "id", None):
            raise JournalEntryCreationError(
                "All postings must belong to the same chart. Cross-chart journal entries are not allowed."
            )

    return chart


def _enforce_period_lock(*, chart, posted_at: datetime) -> None:
    """
    Enforce accounting period locks for this chart.

    IMPORTANT:
    - Lazy import to avoid circular imports during Django app loading.
    - period_lock imports PeriodClose model; models must never import services.
    """
    try:
        from accounting.services.period_lock import (
            PeriodLockedError,
            assert_period_open,
        )
    except Exception as exc:
        raise JournalEntryCreationError(
            "Period lock enforcement is enabled, but period_lock could not be imported."
        ) from exc

    try:
        assert_period_open(chart=chart, posted_at=posted_at)
    except PeriodLockedError as exc:
        raise JournalEntryCreationError(str(exc)) from exc


@transaction.atomic
def create_journal_entry(
    *,
    description: str,
    postings: list,
    reference_type: str | None = None,
    reference_id: str | None = None,
    posted_at: datetime | None = None,
):
    if not postings:
        raise JournalEntryCreationError(
            "Journal entry must contain at least one posting"
        )

    description = (description or "").strip()
    if not description:
        raise JournalEntryCreationError("Journal entry description is required")

    reference = _normalize_reference(reference_type, reference_id)

    total_debits = Decimal("0.00")
    total_credits = Decimal("0.00")
    normalized_postings: list[dict] = []

    for line in postings:
        if not isinstance(line, dict):
            raise JournalEntryCreationError("Each posting must be an object/dict")

        account = line.get("account")
        if account is None:
            raise JournalEntryCreationError("Posting missing account")

        if not getattr(account, "is_active", True):
            raise JournalEntryCreationError(
                f"Account {getattr(account, 'code', 'UNKNOWN')} is inactive"
            )

        debit = _money(line.get("debit"))
        credit = _money(line.get("credit"))

        if debit < 0 or credit < 0:
            raise JournalEntryCreationError("Debit or credit cannot be negative")

        if debit > 0 and credit > 0:
            raise JournalEntryCreationError(
                "A posting cannot have both debit and credit"
            )

        if debit == 0 and credit == 0:
            raise JournalEntryCreationError(
                "A posting must have either debit or credit"
            )

        if debit > 0 and debit < MIN_LINE_AMOUNT:
            raise JournalEntryCreationError(f"Debit amount too small: {debit}")
        if credit > 0 and credit < MIN_LINE_AMOUNT:
            raise JournalEntryCreationError(f"Credit amount too small: {credit}")

        total_debits += debit
        total_credits += credit

        normalized_postings.append(
            {"account": account, "debit": debit, "credit": credit}
        )

    total_debits = total_debits.quantize(TWOPLACES, rounding=ROUND_HALF_UP)
    total_credits = total_credits.quantize(TWOPLACES, rounding=ROUND_HALF_UP)

    if total_debits != total_credits:
        raise JournalEntryCreationError(
            f"Journal entry not balanced: debits={total_debits} credits={total_credits}"
        )

    chart = _infer_chart_from_postings(normalized_postings)
    posted_at_dt = _as_aware_dt(posted_at)

    # ✅ Period lock enforcement (engine choke-point)
    _enforce_period_lock(chart=chart, posted_at=posted_at_dt)

    # Clear error before DB constraint race handling
    if reference and JournalEntry.objects.filter(reference=reference).exists():
        raise IdempotencyError(
            f"Journal entry already exists for reference {reference}"
        )

    try:
        journal_entry = JournalEntry.objects.create(
            description=description,
            reference=reference,
            posted_at=posted_at_dt,
            is_posted=True,
        )
    except IntegrityError as exc:
        if reference and JournalEntry.objects.filter(reference=reference).exists():
            raise IdempotencyError(
                f"Journal entry already exists for reference {reference}"
            ) from exc
        raise JournalEntryCreationError(
            f"Failed to create journal entry: {exc}"
        ) from exc

    ledger_entries: list[LedgerEntry] = []
    for line in normalized_postings:
        debit = line["debit"]
        credit = line["credit"]

        if debit > 0:
            ledger_entries.append(
                LedgerEntry(
                    journal_entry=journal_entry,
                    account=line["account"],
                    entry_type=LedgerEntry.DEBIT,
                    amount=debit,
                )
            )

        if credit > 0:
            ledger_entries.append(
                LedgerEntry(
                    journal_entry=journal_entry,
                    account=line["account"],
                    entry_type=LedgerEntry.CREDIT,
                    amount=credit,
                )
            )

    LedgerEntry.objects.bulk_create(ledger_entries)
    return journal_entry
