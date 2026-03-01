# ============================================================
# PATH: accounting/services/posting_rules_refund.py
# ============================================================

from decimal import Decimal, ROUND_HALF_UP

from accounting.services.account_resolver import (
    get_accounts_receivable_account,
    get_bank_account,
    get_cash_account,
    get_inventory_account,
    get_sales_cogs_account,
    get_sales_discount_account,
    get_sales_revenue_account,
    get_vat_payable_account,
)
from accounting.services.journal_entry_service import create_journal_entry


TWOPLACES = Decimal("0.01")


def _money(value):
    return Decimal(value or 0).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def _resolve_payout_account(method):
    method = (method or "cash").lower()
    if method == "cash":
        return get_cash_account()
    if method in ("card", "bank", "transfer", "pos"):
        return get_bank_account()
    if method in ("credit", "invoice", "on_account"):
        return get_accounts_receivable_account()
    return get_cash_account()


def post_pos_refund(*, refund_audit):

    subtotal = _money(refund_audit.subtotal_amount)
    tax = _money(refund_audit.tax_amount)
    discount = _money(refund_audit.discount_amount)
    total = _money(refund_audit.total_amount)
    cogs = _money(refund_audit.cogs_amount)

    sale = refund_audit.sale
    payout_account = _resolve_payout_account(sale.payment_method)

    postings = []

    if subtotal > 0:
        postings.append({"account": get_sales_revenue_account(), "debit": subtotal, "credit": 0})

    if tax > 0:
        postings.append({"account": get_vat_payable_account(), "debit": tax, "credit": 0})

    if discount > 0:
        postings.append({"account": get_sales_discount_account(), "debit": 0, "credit": discount})

    if total > 0:
        postings.append({"account": payout_account, "debit": 0, "credit": total})

    # Reverse COGS properly
    if cogs > 0:
        postings.append({"account": get_inventory_account(), "debit": cogs, "credit": 0})
        postings.append({"account": get_sales_cogs_account(), "debit": 0, "credit": cogs})

    return create_journal_entry(
        description=f"POS Refund {sale.invoice_no}",
        postings=postings,
        reference_type="POS_REFUND",
        reference_id=str(refund_audit.id),
    )