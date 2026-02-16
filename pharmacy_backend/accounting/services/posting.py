# accounting/services/posting.py

"""
======================================================
PATH: accounting/services/posting.py
======================================================
POSTING ADAPTER

Build postings and call create_journal_entry (the engine).

This module should remain a thin adapter:
- It DOES NOT do workflows (orchestrators do).
- It DOES map business events -> accounting postings.
- It ALWAYS calls create_journal_entry (engine) for immutability + idempotency.

HOTSPRINT UPGRADE (PURCHASE-COST + PROFIT READY):
- Post SALE includes BOTH:
  (1) Revenue side: Cash/Bank/AR, Revenue, VAT, Discount
  (2) Cost side: COGS + Inventory reduction (computed from StockMovement cost snapshots)
- Post REFUND includes reverse of BOTH sides (computed from StockMovement cost snapshots)

SPLIT PAYMENT UPGRADE:
- If sale.payment_method == "split", we post multiple payment legs:
    Debit:   Cash/Bank/AR per allocation method
    Credit: Revenue/VAT (and Debit discount if any) as usual
- Refund reverses those exact legs:
    Credit: Cash/Bank/AR per allocation method
    Debit:  Revenue/VAT (and Credit discount if any) as usual

PARTIAL REFUND UPGRADE:
- post_partial_refund_to_ledger() posts a proportional reversal for a subset of items.
- Tax + discount are prorated using refunded_subtotal / sale.subtotal_amount.
- COGS/Inventory reversal uses refund item snapshots (unit_cost_snapshot * qty).

AUDIT RULE:
- If a sale has SALE stock movements but any movement has NULL unit_cost_snapshot,
  we hard-fail cost posting (we refuse to invent cost).

PERIOD LOCK INTEGRATION (Hour 4–8):
- Before creating any journal entry, we *optionally* pre-check that posted_at is not inside a closed period.
- Enforcement uses accounting/services/period_lock.py (assert_period_open(chart=..., posted_at=...)).
- If posted_at is None, we skip enforcement (legacy-safe).
- If chart cannot be inferred here, we DO NOT guess; we let the engine enforce locks (engine is the choke-point).
"""

from __future__ import annotations

import hashlib
from datetime import datetime, time
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable, Any

from django.db.models import Sum, F, DecimalField
from django.db.models.expressions import ExpressionWrapper
from django.utils import timezone

from accounting.services.journal_entry_service import create_journal_entry

# Alias for backward compatibility (older code may import post_journal_entry)
post_journal_entry = create_journal_entry

TWOPLACES = Decimal("0.01")
RATIO_PLACES = Decimal("0.0000001")


def _money(v) -> Decimal:
    if v is None or v == "":
        return Decimal("0.00")
    return Decimal(str(v)).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def _end_of_day_aware(d) -> datetime:
    dt = datetime.combine(d, time(23, 59, 59))
    if timezone.is_naive(dt):
        return timezone.make_aware(dt, timezone.get_current_timezone())
    return dt


def _best_effort_posted_at_from_obj(obj, *, fallback_date=None) -> datetime | None:
    for attr in ("posted_at", "completed_at", "sold_at", "paid_at", "created_at"):
        v = getattr(obj, attr, None)
        if isinstance(v, datetime):
            if timezone.is_naive(v):
                return timezone.make_aware(v, timezone.get_current_timezone())
            return v

    if fallback_date is not None:
        try:
            return _end_of_day_aware(fallback_date)
        except Exception:
            return None

    return None


def _infer_chart_from_postings(postings: list[dict]) -> object | None:
    """
    Best-effort chart inference from postings accounts.

    Rules:
    - All accounts must belong to same chart (by chart_id)
    - If missing, return None (caller decides behavior)
    """
    if not postings:
        return None

    first_account = postings[0].get("account")
    if first_account is None:
        return None

    chart = getattr(first_account, "chart", None)
    chart_id = getattr(first_account, "chart_id", None) or getattr(chart, "id", None)

    if chart is None and chart_id is None:
        return None

    for line in postings[1:]:
        acc = line.get("account")
        if acc is None:
            continue
        acc_chart = getattr(acc, "chart", None)
        acc_chart_id = getattr(acc, "chart_id", None) or getattr(acc_chart, "id", None)
        if chart_id is not None and acc_chart_id is not None and acc_chart_id != chart_id:
            raise ValueError("Cross-chart postings are not allowed (chart mismatch across posting lines).")

    # Return the chart object only if we actually have it; otherwise None (no guessing).
    return chart


def _enforce_period_open(*, chart, posted_at: datetime | None) -> None:
    """
    Pre-check: Enforce that we are not posting into a locked/closed period.

    - If posted_at is None -> skip (legacy-safe)
    - chart must be provided (explicit; never guessed incorrectly)
    - If chart is None -> skip and let the engine enforce (engine infers chart reliably from postings)
    """
    if posted_at is None:
        return
    if chart is None:
        return

    from accounting.services.period_lock import assert_period_open, PeriodLockedError

    try:
        assert_period_open(chart=chart, posted_at=posted_at)
    except PeriodLockedError as exc:
        raise ValueError(str(exc)) from exc


def _resolve_account_for_method(method: str):
    """
    Resolve the correct debit/credit account for a payment leg method.

    Mapping:
    - cash     -> Cash
    - bank     -> Bank
    - pos      -> Bank (POS settles into bank)
    - transfer -> Bank
    - card     -> Bank
    - credit   -> Accounts Receivable
    """
    from accounting.services.account_resolver import (
        get_cash_account,
        get_bank_account,
        get_accounts_receivable_account,
    )

    m = (method or "").strip().lower()
    if m == "cash":
        return get_cash_account()
    if m in ("bank", "pos", "transfer", "card"):
        return get_bank_account()
    if m in ("credit", "invoice", "on_account", "ar"):
        return get_accounts_receivable_account()

    return get_cash_account()


def _resolve_debit_account_for_payment_method(*, sale):
    method = (getattr(sale, "payment_method", "") or "cash").lower().strip()
    return _resolve_account_for_method(method)


def _require_cost_accounts():
    try:
        from accounting.services.account_resolver import (
            get_inventory_account,
            get_cogs_account,
        )
    except Exception as exc:
        raise ValueError(
            "COGS posting requires account_resolver functions: "
            "get_inventory_account() and get_cogs_account()."
        ) from exc

    return get_inventory_account(), get_cogs_account()


def _compute_sale_cogs_from_movements(*, sale) -> Decimal:
    """
    Compute total sale COGS from SALE stock movements (authoritative).
    """
    from products.models import StockMovement

    sale_movements = StockMovement.objects.filter(
        sale=sale,
        reason=StockMovement.Reason.SALE,
        movement_type=StockMovement.MovementType.OUT,
    )

    if not sale_movements.exists():
        return Decimal("0.00")

    if sale_movements.filter(unit_cost_snapshot__isnull=True).exists():
        raise ValueError(
            f"Cannot compute COGS for sale {getattr(sale, 'id', sale)}: "
            "some StockMovement rows are missing unit_cost_snapshot. "
            "Backfill batch unit_cost for legacy stock, then re-run the cost backfill command."
        )

    total_expr = ExpressionWrapper(
        F("quantity") * F("unit_cost_snapshot"),
        output_field=DecimalField(max_digits=18, decimal_places=2),
    )

    agg = sale_movements.aggregate(total=Sum(total_expr)).get("total")
    return _money(agg or Decimal("0.00"))


def _merge_postings_by_account(postings: list[dict]) -> list[dict]:
    """
    Combine postings with the same account (keeps journal tidy).
    """
    merged: dict[Any, dict[str, Any]] = {}
    for p in postings:
        acct = p["account"]
        debit = _money(p.get("debit", 0))
        credit = _money(p.get("credit", 0))
        if acct not in merged:
            merged[acct] = {"account": acct, "debit": Decimal("0.00"), "credit": Decimal("0.00")}
        merged[acct]["debit"] = _money(merged[acct]["debit"] + debit)
        merged[acct]["credit"] = _money(merged[acct]["credit"] + credit)

    out: list[dict] = []
    for p in merged.values():
        if p["debit"] != Decimal("0.00") or p["credit"] != Decimal("0.00"):
            out.append(p)
    return out


def _get_split_allocations_or_none(*, sale):
    """
    Returns allocations for split payments:
      [{method: str, amount: Decimal}, ...]
    or None if not split mode.

    Hard rules:
    - allocations must exist when sale.payment_method == "split"
    - sum(amount) must equal sale.total_amount (2dp exact)
    """
    pm = (getattr(sale, "payment_method", "") or "").strip().lower()
    if pm != "split":
        return None

    from sales.models.sale_payment_allocation import SalePaymentAllocation

    allocs = list(SalePaymentAllocation.objects.filter(sale=sale).order_by("created_at", "id"))
    if not allocs:
        raise ValueError(
            f"Sale {getattr(sale, 'id', sale)} is marked as split payment "
            "but has no payment allocations."
        )

    out = []
    for a in allocs:
        method = (getattr(a, "method", "") or "").strip().lower()
        amount = _money(getattr(a, "amount", None))
        if amount <= Decimal("0.00"):
            raise ValueError("Split payment allocation amount must be > 0")
        out.append({"method": method, "amount": amount})

    alloc_total = _money(sum((x["amount"] for x in out), Decimal("0.00")))
    total = _money(getattr(sale, "total_amount", None))
    if alloc_total != total:
        raise ValueError(
            f"Split payment allocations sum({alloc_total}) != sale total({total}) "
            f"for sale {getattr(sale, 'id', sale)}"
        )

    return out


def _prorate(*, amount: Decimal, ratio: Decimal) -> Decimal:
    amount = _money(amount)
    if amount <= Decimal("0.00"):
        return Decimal("0.00")

    if ratio <= Decimal("0.00"):
        return Decimal("0.00")

    if ratio >= Decimal("1.00"):
        return amount

    return _money(amount * ratio)


def _partial_refund_reference_id(*, sale, refund_items: Iterable[Any]) -> str:
    """
    Deterministic idempotency key for a given partial-refund shape.

    NOTE:
    We include: sale_item_id, quantity, unit_price_snapshot, unit_cost_snapshot.
    This makes retries safe and blocks accidental double-posting.
    """
    parts: list[str] = []

    for r in refund_items:
        sid = str(getattr(r, "sale_item_id", "") or "")
        qty = int(getattr(r, "quantity_refunded", 0) or 0)
        up = _money(getattr(r, "unit_price_snapshot", None))
        uc = _money(getattr(r, "unit_cost_snapshot", None))
        parts.append(f"{sid}:{qty}:{up}:{uc}")

    parts.sort()
    base = f"{getattr(sale, 'id', sale)}|" + "|".join(parts)
    digest = hashlib.sha1(base.encode("utf-8")).hexdigest()[:24]
    return f"{getattr(sale, 'id', sale)}:PR:{digest}"


# ============================================================
# POS SALE POSTING
# ============================================================

def post_sale_to_ledger(*, sale):
    from accounting.services.account_resolver import (
        get_sales_revenue_account,
        get_sales_discount_account,
        get_vat_payable_account,
    )

    revenue_account = getattr(sale, "revenue_account", None) or get_sales_revenue_account()
    vat_account = getattr(sale, "vat_account", None) or get_vat_payable_account()

    total = _money(getattr(sale, "total_amount", None))
    subtotal = _money(getattr(sale, "subtotal_amount", None))
    tax = _money(getattr(sale, "tax_amount", None))
    discount = _money(getattr(sale, "discount_amount", None))

    expected_total = (subtotal + tax - discount).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
    if expected_total != total:
        raise ValueError(
            f"Sale totals mismatch: subtotal({subtotal}) + tax({tax}) - discount({discount}) != total({total})"
        )

    postings: list[dict] = []
    split_allocs = _get_split_allocations_or_none(sale=sale)

    # Debit side (cash/bank/ar)
    if total > Decimal("0.00"):
        if split_allocs:
            for leg in split_allocs:
                acct = _resolve_account_for_method(leg["method"])
                amt = _money(leg["amount"])
                postings.append({"account": acct, "debit": amt, "credit": Decimal("0.00")})
        else:
            debit_account = getattr(sale, "cash_account", None) or _resolve_debit_account_for_payment_method(sale=sale)
            postings.append({"account": debit_account, "debit": total, "credit": Decimal("0.00")})

    # Discount (debit)
    if discount > Decimal("0.00"):
        discount_account = getattr(sale, "discount_account", None) or get_sales_discount_account()
        postings.append({"account": discount_account, "debit": discount, "credit": Decimal("0.00")})

    # Revenue (credit)
    if subtotal > Decimal("0.00"):
        postings.append({"account": revenue_account, "debit": Decimal("0.00"), "credit": subtotal})

    # VAT (credit)
    if tax > Decimal("0.00"):
        postings.append({"account": vat_account, "debit": Decimal("0.00"), "credit": tax})

    # Cost side
    cogs = _compute_sale_cogs_from_movements(sale=sale)
    if cogs > Decimal("0.00"):
        inventory_account, cogs_account = _require_cost_accounts()
        postings.append({"account": cogs_account, "debit": cogs, "credit": Decimal("0.00")})
        postings.append({"account": inventory_account, "debit": Decimal("0.00"), "credit": cogs})

    postings = _merge_postings_by_account(postings)
    posted_at = _best_effort_posted_at_from_obj(sale)

    chart = _infer_chart_from_postings(postings)
    _enforce_period_open(chart=chart, posted_at=posted_at)

    return create_journal_entry(
        description=f"POS Sale {getattr(sale, 'invoice_no', sale.id)}",
        postings=postings,
        reference_type="POS_SALE",
        reference_id=str(sale.id),
        posted_at=posted_at,
    )


# ============================================================
# POS REFUND POSTING (FULL)
# ============================================================

def post_refund_to_ledger(*, sale, refund_audit):
    from accounting.services.account_resolver import (
        get_sales_revenue_account,
        get_sales_discount_account,
        get_vat_payable_account,
    )

    revenue_account = getattr(sale, "revenue_account", None) or get_sales_revenue_account()
    vat_account = getattr(sale, "vat_account", None) or get_vat_payable_account()

    raw_total = (
        getattr(refund_audit, "original_total_amount", None)
        or getattr(refund_audit, "total_amount", None)
        or getattr(refund_audit, "amount", None)
        or getattr(sale, "total_amount", None)
    )
    if raw_total in (None, "", 0, "0", "0.00"):
        raise ValueError(
            "Refund total amount is missing on refund_audit "
            "(expected original_total_amount/total_amount/amount)."
        )

    total = _money(raw_total)

    subtotal = _money(
        getattr(refund_audit, "original_subtotal_amount", None)
        or getattr(refund_audit, "subtotal_amount", None)
        or getattr(sale, "subtotal_amount", None)
    )
    tax = _money(
        getattr(refund_audit, "original_tax_amount", None)
        or getattr(refund_audit, "tax_amount", None)
        or getattr(sale, "tax_amount", None)
    )
    discount = _money(
        getattr(refund_audit, "original_discount_amount", None)
        or getattr(refund_audit, "discount_amount", None)
        or getattr(sale, "discount_amount", None)
    )

    expected_total = (subtotal + tax - discount).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
    if expected_total != total:
        raise ValueError(
            f"Refund totals mismatch: subtotal({subtotal}) + tax({tax}) - discount({discount}) != total({total})"
        )

    postings: list[dict] = []

    # Reverse revenue
    if subtotal > Decimal("0.00"):
        postings.append({"account": revenue_account, "debit": subtotal, "credit": Decimal("0.00")})

    if tax > Decimal("0.00"):
        postings.append({"account": vat_account, "debit": tax, "credit": Decimal("0.00")})

    if discount > Decimal("0.00"):
        discount_account = getattr(sale, "discount_account", None) or get_sales_discount_account()
        postings.append({"account": discount_account, "debit": Decimal("0.00"), "credit": discount})

    # Credit payment accounts back
    split_allocs = _get_split_allocations_or_none(sale=sale)
    if total > Decimal("0.00"):
        if split_allocs:
            for leg in split_allocs:
                acct = _resolve_account_for_method(leg["method"])
                amt = _money(leg["amount"])
                postings.append({"account": acct, "debit": Decimal("0.00"), "credit": amt})
        else:
            credit_account = getattr(sale, "cash_account", None) or _resolve_debit_account_for_payment_method(sale=sale)
            postings.append({"account": credit_account, "debit": Decimal("0.00"), "credit": total})

    # Reverse COGS (full)
    cogs = _compute_sale_cogs_from_movements(sale=sale)
    if cogs > Decimal("0.00"):
        inventory_account, cogs_account = _require_cost_accounts()
        postings.append({"account": inventory_account, "debit": cogs, "credit": Decimal("0.00")})
        postings.append({"account": cogs_account, "debit": Decimal("0.00"), "credit": cogs})

    postings = _merge_postings_by_account(postings)
    posted_at = _best_effort_posted_at_from_obj(refund_audit) or _best_effort_posted_at_from_obj(sale)

    chart = _infer_chart_from_postings(postings)
    _enforce_period_open(chart=chart, posted_at=posted_at)

    refund_ref_id = str(getattr(refund_audit, "id", refund_audit))

    return create_journal_entry(
        description=f"POS Refund {getattr(sale, 'invoice_no', sale.id)}",
        postings=postings,
        reference_type="POS_REFUND",
        reference_id=refund_ref_id,
        posted_at=posted_at,
    )


# ============================================================
# POS PARTIAL REFUND POSTING
# ============================================================

def post_partial_refund_to_ledger(*, sale, refund_items: Iterable[Any]):
    """
    Proportional reversal for a subset of items.

    Proration basis:
    - ratio = refunded_subtotal / sale.subtotal_amount
    - prorated_tax = sale.tax_amount * ratio
    - prorated_discount = sale.discount_amount * ratio

    Payment legs:
    - If split, credit legs proportionally by (refund_total / sale.total_amount),
      with last-leg rounding correction.

    Cost side:
    - Uses refund item snapshots (unit_cost_snapshot * qty) — deterministic.
    """
    from accounting.services.account_resolver import (
        get_sales_revenue_account,
        get_sales_discount_account,
        get_vat_payable_account,
    )

    refund_items = list(refund_items or [])
    if not refund_items:
        raise ValueError("refund_items is required for partial refund posting")

    revenue_account = getattr(sale, "revenue_account", None) or get_sales_revenue_account()
    vat_account = getattr(sale, "vat_account", None) or get_vat_payable_account()

    sale_subtotal = _money(getattr(sale, "subtotal_amount", None))
    sale_tax = _money(getattr(sale, "tax_amount", None))
    sale_discount = _money(getattr(sale, "discount_amount", None))
    sale_total = _money(getattr(sale, "total_amount", None))

    if sale_total <= Decimal("0.00"):
        raise ValueError("Sale total must be > 0 to post a refund")

    refunded_subtotal = Decimal("0.00")
    refunded_cogs = Decimal("0.00")

    for r in refund_items:
        qty = int(getattr(r, "quantity_refunded", 0) or 0)
        if qty <= 0:
            raise ValueError("Refund item quantity_refunded must be > 0")

        unit_price = _money(getattr(r, "unit_price_snapshot", None))
        unit_cost = _money(getattr(r, "unit_cost_snapshot", None))

        refunded_subtotal += (unit_price * Decimal(qty))
        refunded_cogs += (unit_cost * Decimal(qty))

    refunded_subtotal = _money(refunded_subtotal)
    refunded_cogs = _money(refunded_cogs)

    if refunded_subtotal <= Decimal("0.00"):
        raise ValueError("Computed refunded_subtotal is 0; nothing to post")

    ratio = Decimal("0.00")
    if sale_subtotal > Decimal("0.00"):
        ratio = (refunded_subtotal / sale_subtotal).quantize(RATIO_PLACES, rounding=ROUND_HALF_UP)

    prorated_tax = _prorate(amount=sale_tax, ratio=ratio)
    prorated_discount = _prorate(amount=sale_discount, ratio=ratio)

    refund_total = _money(refunded_subtotal + prorated_tax - prorated_discount)
    if refund_total <= Decimal("0.00"):
        raise ValueError("Computed refund_total is <= 0; cannot post partial refund")

    postings: list[dict] = []

    # Reverse revenue portion
    postings.append({"account": revenue_account, "debit": refunded_subtotal, "credit": Decimal("0.00")})

    if prorated_tax > Decimal("0.00"):
        postings.append({"account": vat_account, "debit": prorated_tax, "credit": Decimal("0.00")})

    if prorated_discount > Decimal("0.00"):
        discount_account = getattr(sale, "discount_account", None) or get_sales_discount_account()
        postings.append({"account": discount_account, "debit": Decimal("0.00"), "credit": prorated_discount})

    # Payment credits back
    split_allocs = _get_split_allocations_or_none(sale=sale)
    if split_allocs:
        leg_ratio = (refund_total / sale_total).quantize(RATIO_PLACES, rounding=ROUND_HALF_UP)

        credited_sum = Decimal("0.00")
        last_idx = len(split_allocs) - 1

        for idx, leg in enumerate(split_allocs):
            acct = _resolve_account_for_method(leg["method"])
            leg_amt = _money(leg["amount"])

            share = _money(leg_amt * leg_ratio)
            if idx == last_idx:
                share = _money(refund_total - credited_sum)

            if share > Decimal("0.00"):
                postings.append({"account": acct, "debit": Decimal("0.00"), "credit": share})
                credited_sum = _money(credited_sum + share)

        if _money(credited_sum) != refund_total:
            raise ValueError(
                f"Split partial refund credit mismatch: credited_sum({credited_sum}) != refund_total({refund_total})"
            )
    else:
        credit_account = getattr(sale, "cash_account", None) or _resolve_debit_account_for_payment_method(sale=sale)
        postings.append({"account": credit_account, "debit": Decimal("0.00"), "credit": refund_total})

    # Reverse COGS using refund snapshots (authoritative)
    if refunded_cogs > Decimal("0.00"):
        inventory_account, cogs_account = _require_cost_accounts()
        postings.append({"account": inventory_account, "debit": refunded_cogs, "credit": Decimal("0.00")})
        postings.append({"account": cogs_account, "debit": Decimal("0.00"), "credit": refunded_cogs})

    postings = _merge_postings_by_account(postings)
    posted_at = _best_effort_posted_at_from_obj(sale)
    reference_id = _partial_refund_reference_id(sale=sale, refund_items=refund_items)

    chart = _infer_chart_from_postings(postings)
    _enforce_period_open(chart=chart, posted_at=posted_at)

    return create_journal_entry(
        description=f"POS Partial Refund {getattr(sale, 'invoice_no', sale.id)}",
        postings=postings,
        reference_type="POS_PARTIAL_REFUND",
        reference_id=reference_id,
        posted_at=posted_at,
    )


# ============================================================
# OPENING BALANCES
# ============================================================

def post_opening_balances_to_ledger(
    *,
    business_id: str,
    chart_id: str | None,
    as_of_date,
    postings: list,
):
    ref_id = f"{business_id}:{chart_id}" if chart_id else str(business_id)
    desc_date = getattr(as_of_date, "isoformat", lambda: str(as_of_date))()
    description = f"Opening Balances as of {desc_date}"

    posted_at = None
    try:
        posted_at = _end_of_day_aware(as_of_date)
    except Exception:
        posted_at = None

    chart = _infer_chart_from_postings(postings)
    _enforce_period_open(chart=chart, posted_at=posted_at)

    return create_journal_entry(
        description=description,
        postings=postings,
        reference_type="OPENING_BALANCE",
        reference_id=ref_id,
        posted_at=posted_at,
    )


# ============================================================
# EXPENSES
# ============================================================

def post_expense_to_ledger(
    *,
    expense_id: str,
    expense_date,
    narration: str,
    expense_account,
    payment_account,
    amount,
):
    amt = _money(amount)
    if amt <= Decimal("0.00"):
        raise ValueError("Expense amount must be > 0")

    desc_date = getattr(expense_date, "isoformat", lambda: str(expense_date))()
    description = f"Expense ({desc_date}) - {narration}".strip()

    postings = [
        {"account": expense_account, "debit": amt, "credit": Decimal("0.00")},
        {"account": payment_account, "debit": Decimal("0.00"), "credit": amt},
    ]

    posted_at = None
    try:
        posted_at = _end_of_day_aware(expense_date)
    except Exception:
        posted_at = None

    chart = _infer_chart_from_postings(postings)
    _enforce_period_open(chart=chart, posted_at=posted_at)

    return create_journal_entry(
        description=description,
        postings=postings,
        reference_type="EXPENSE",
        reference_id=str(expense_id),
        posted_at=posted_at,
    )


# ============================================================
# PURCHASE RECEIPTS (STOCK IN)
# ============================================================

def post_purchase_receipt_to_ledger(
    *,
    invoice_id: str,
    invoice_number: str,
    received_date,
    inventory_account,
    payable_account,
    amount,
):
    amt = _money(amount)
    if amt <= Decimal("0.00"):
        raise ValueError("Purchase receipt amount must be > 0")

    d = getattr(received_date, "isoformat", lambda: str(received_date))()
    description = f"Purchase Receipt {invoice_number} ({d})"

    postings = [
        {"account": inventory_account, "debit": amt, "credit": Decimal("0.00")},
        {"account": payable_account, "debit": Decimal("0.00"), "credit": amt},
    ]

    posted_at = None
    try:
        posted_at = _end_of_day_aware(received_date)
    except Exception:
        posted_at = None

    chart = _infer_chart_from_postings(postings)
    _enforce_period_open(chart=chart, posted_at=posted_at)

    return create_journal_entry(
        description=description,
        postings=postings,
        reference_type="PURCHASE_RECEIPT",
        reference_id=str(invoice_id),
        posted_at=posted_at,
    )


# ============================================================
# SUPPLIER PAYMENTS (SETTLE ACCOUNTS PAYABLE)
# ============================================================

def post_supplier_payment_to_ledger(
    *,
    payment_id: str,
    payment_date,
    payable_account,
    payment_account,
    amount,
    supplier_name: str = "",
    invoice_number: str = "",
):
    amt = _money(amount)
    if amt <= Decimal("0.00"):
        raise ValueError("Payment amount must be > 0")

    d = getattr(payment_date, "isoformat", lambda: str(payment_date))()
    suffix = ""
    if supplier_name:
        suffix += f" - {supplier_name}"
    if invoice_number:
        suffix += f" ({invoice_number})"

    description = f"Supplier Payment {d}{suffix}".strip()

    postings = [
        {"account": payable_account, "debit": amt, "credit": Decimal("0.00")},
        {"account": payment_account, "debit": Decimal("0.00"), "credit": amt},
    ]

    posted_at = None
    try:
        posted_at = _end_of_day_aware(payment_date)
    except Exception:
        posted_at = None

    chart = _infer_chart_from_postings(postings)
    _enforce_period_open(chart=chart, posted_at=posted_at)

    return create_journal_entry(
        description=description,
        postings=postings,
        reference_type="SUPPLIER_PAYMENT",
        reference_id=str(payment_id),
        posted_at=posted_at,
    )


# ============================================================
# BACKWARD-COMPAT ALIASES (do not remove)
# ============================================================

post_purchase_invoice_to_ledger = post_purchase_receipt_to_ledger
post_purchase_to_ledger = post_purchase_receipt_to_ledger
