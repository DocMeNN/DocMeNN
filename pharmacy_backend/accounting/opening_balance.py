# accounting/opening_balance.py

"""
PATH: accounting/opening_balance.py

OPENING BALANCE DOMAIN (FRAMEWORK-AGNOSTIC)

Purpose:
- Provide a single, authoritative validation + normalization layer for Opening Balances.
- Used by BOTH:
  - DRF serializer validation (API layer)
  - service posting logic (application layer)

Rules:
- Every line must have account_code, dc ("D" or "C"), amount > 0
- No duplicate account codes (strict)
- Debits must equal credits (balanced)
- Money normalized to 2dp

Idempotency Reference:
- reference_id format (service layer uses):
  "<business_id>:<chart_id>:<as_of_date>"
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Iterable, List, Optional, Tuple

MONEY_QUANT = Decimal("0.01")


class OpeningBalanceError(ValueError):
    """Raised when the opening balance payload is invalid."""


def _to_decimal(value) -> Decimal:
    try:
        if isinstance(value, Decimal):
            d = value
        else:
            d = Decimal(str(value))
    except (InvalidOperation, TypeError) as e:
        raise OpeningBalanceError(f"Invalid amount: {value!r}") from e

    return d.quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)


def build_opening_balance_reference_id(
    *,
    business_id: int | str,
    chart_id: int | str,
    as_of_date: date,
) -> str:
    """
    Build service-level reference_id string for idempotent posting.

    reference_id = "<business_id>:<chart_id>:<as_of_date>"
    """
    if business_id is None or str(business_id).strip() == "":
        raise OpeningBalanceError("business_id is required")
    if chart_id is None or str(chart_id).strip() == "":
        raise OpeningBalanceError("chart_id is required")
    if not isinstance(as_of_date, date):
        raise OpeningBalanceError("as_of_date must be a date")

    return f"{str(business_id).strip()}:{str(chart_id).strip()}:{as_of_date.isoformat()}"


@dataclass(frozen=True)
class OpeningBalanceLine:
    """
    One opening balance line.

    - account_code: chart account code (string)
    - dc: "D" for debit, "C" for credit
    - amount: Decimal money (2dp)
    """

    account_code: str
    dc: str
    amount: Decimal

    @staticmethod
    def from_raw(raw: dict, *, index: int | None = None) -> "OpeningBalanceLine":
        if not isinstance(raw, dict):
            prefix = f"Line {index} " if index is not None else ""
            raise OpeningBalanceError(f"{prefix}must be an object/dict")

        account_code = (raw.get("account_code") or "").strip()
        if not account_code:
            prefix = f"Line {index} " if index is not None else ""
            raise OpeningBalanceError(f"{prefix}account_code is required")

        dc = (raw.get("dc") or "").strip().upper()
        if dc not in ("D", "C"):
            raise OpeningBalanceError(f"dc must be 'D' or 'C', got {raw.get('dc')!r}")

        amount = _to_decimal(raw.get("amount"))
        if amount <= Decimal("0.00"):
            raise OpeningBalanceError(f"amount must be > 0 for account {account_code}")

        return OpeningBalanceLine(account_code=account_code, dc=dc, amount=amount)


@dataclass(frozen=True)
class OpeningBalancePayload:
    """
    Validated opening balances payload (domain object).

    - business_id: owning business identifier
    - as_of_date: opening balance "as at" date (posting is end-of-day)
    - lines: tuple of validated OpeningBalanceLine
    """

    business_id: int | str
    as_of_date: date
    lines: Tuple[OpeningBalanceLine, ...]

    @staticmethod
    def from_raw(
        *,
        business_id: int | str,
        as_of_date: date,
        raw_lines: Iterable[dict],
    ) -> "OpeningBalancePayload":
        if business_id is None or str(business_id).strip() == "":
            raise OpeningBalanceError("business_id is required")

        if not isinstance(as_of_date, date):
            raise OpeningBalanceError("as_of_date must be a date")

        lines_list: List[OpeningBalanceLine] = []
        for i, raw in enumerate(raw_lines or []):
            lines_list.append(OpeningBalanceLine.from_raw(raw, index=i))

        if not lines_list:
            raise OpeningBalanceError("At least one line is required")

        payload = OpeningBalancePayload(
            business_id=business_id,
            as_of_date=as_of_date,
            lines=tuple(lines_list),
        )
        payload.validate_no_duplicate_accounts()
        payload.validate_balanced()
        return payload

    def totals(self) -> Tuple[Decimal, Decimal]:
        debit = sum((l.amount for l in self.lines if l.dc == "D"), start=Decimal("0.00"))
        credit = sum((l.amount for l in self.lines if l.dc == "C"), start=Decimal("0.00"))
        debit = debit.quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)
        credit = credit.quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)
        return debit, credit

    def validate_balanced(self) -> None:
        debit, credit = self.totals()
        if debit != credit:
            raise OpeningBalanceError(
                f"Opening balances must balance. Debits={debit} Credits={credit}"
            )

    def validate_no_duplicate_accounts(self) -> None:
        seen = set()
        for l in self.lines:
            if l.account_code in seen:
                raise OpeningBalanceError(f"Duplicate account_code in lines: {l.account_code}")
            seen.add(l.account_code)
