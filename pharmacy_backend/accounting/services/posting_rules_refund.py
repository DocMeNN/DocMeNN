# accounting/services/posting_rules_refund.py

"""
POSTING RULES — POS REFUNDS

Refunds are first-class accounting events.

Accounting Effect:
- Debit  Sales Revenue (reverse revenue)
- Debit  VAT Payable (reverse tax liability)
- Credit Cash/Bank/AR (payout source based on payment method)
- Credit Sales Discounts (reverse discount contra-revenue) [if discount existed]

IMPORTANT:
- This module only BUILDS postings.
- The accounting engine (create_journal_entry) enforces balancing + idempotency.
"""

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from accounting.services.account_resolver import (
    get_accounts_receivable_account,
    get_bank_account,
    get_cash_account,
    get_sales_discount_account,
    get_sales_revenue_account,
    get_vat_payable_account,
)
from accounting.services.exceptions import PostingRuleError
from accounting.services.journal_entry_service import create_journal_entry

TWOPLACES = Decimal("0.01")


def _money(value) -> Decimal:
    """
    Safe money coercion to Decimal(2dp).

    Accepts Decimal/int/str/float (float discouraged).
    """
    if value is None or value == "":
        return Decimal("0.00")

    if isinstance(value, Decimal):
        amt = value
    else:
        try:
            amt = Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError):
            raise PostingRuleError(f"Invalid money value: {value!r}")

    return amt.quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def _resolve_refund_payout_account(*, payment_method: str | None):
    """
    Decide which account is credited when refund is paid out.
    """
    method = (payment_method or "cash").lower().strip()

    if method == "cash":
        return get_cash_account()

    if method in ("card", "transfer", "bank"):
        return get_bank_account()

    if method in ("credit", "invoice", "on_account"):
        # Refund reduces what customer owes (AR)
        return get_accounts_receivable_account()

    # Safe fallback
    return get_cash_account()


def post_pos_refund(*, refund_audit):
    """
    POST SALE REFUND AUDIT → ACCOUNTING

    Expected object: SaleRefundAudit instance with:
    - refund_audit.sale (Sale)
    - refund_audit.id (UUID)
    - refund_audit.original_total_amount (snapshot)
    """

    if refund_audit is None or getattr(refund_audit, "sale", None) is None:
        raise PostingRuleError("refund_audit with attached sale is required")

    sale = refund_audit.sale

    subtotal = _money(getattr(sale, "subtotal_amount", None))
    tax = _money(getattr(sale, "tax_amount", None))
    discount = _money(getattr(sale, "discount_amount", None))

    # Prefer audited snapshot total; fallback to sale.total_amount
    total = _money(
        getattr(refund_audit, "original_total_amount", None)
        or getattr(sale, "total_amount", None)
    )

    # Sanity: subtotal + tax - discount should equal total (2dp)
    expected_total = _money(subtotal + tax - discount)
    if expected_total != total:
        raise PostingRuleError(
            "Refund totals mismatch: "
            f"subtotal({subtotal}) + tax({tax}) - discount({discount}) != total({total})"
        )

    postings = []

    # Debit Revenue (reverse revenue)
    if subtotal > Decimal("0.00"):
        postings.append(
            {
                "account": get_sales_revenue_account(),
                "debit": subtotal,
                "credit": Decimal("0.00"),
            }
        )

    # Debit VAT Payable (reverse tax liability)
    if tax > Decimal("0.00"):
        postings.append(
            {
                "account": get_vat_payable_account(),
                "debit": tax,
                "credit": Decimal("0.00"),
            }
        )

    # Credit Sales Discounts (reverse discount, if any)
    # Sales posting debits discount; refund should credit it back.
    if discount > Decimal("0.00"):
        postings.append(
            {
                "account": get_sales_discount_account(),
                "debit": Decimal("0.00"),
                "credit": discount,
            }
        )

    # Credit payout source (cash/bank/ar)
    payout_account = _resolve_refund_payout_account(
        payment_method=getattr(sale, "payment_method", None)
    )

    if total > Decimal("0.00"):
        postings.append(
            {
                "account": payout_account,
                "debit": Decimal("0.00"),
                "credit": total,
            }
        )

    # Engine enforces balancing + idempotency via reference
    return create_journal_entry(
        description=f"POS Refund {getattr(sale, 'invoice_no', '')}".strip(),
        postings=postings,
        reference_type="POS_REFUND",
        reference_id=str(getattr(refund_audit, "id", "")),
    )
