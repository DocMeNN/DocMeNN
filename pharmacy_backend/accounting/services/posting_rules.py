# accounting/services/posting_rules.py

"""
POSTING RULES — POS SALES (AUTHORITATIVE)

Defines HOW a POS sale maps to accounting intent.

RESPONSIBILITIES:
- Resolve semantic accounts
- Construct debit / credit postings
- Delegate persistence to posting adapter

THIS MODULE DOES NOT:
- Write to the database
- Create JournalEntry directly
- Touch LedgerEntry directly
- Enforce debit == credit math
"""

from decimal import Decimal

from accounting.services.account_resolver import (
    get_cash_account,
    get_sales_revenue_account,
    get_vat_payable_account,
)
from accounting.services.posting import post_journal_entry


def post_pos_sale(sale):
    """
    POST POS SALE → ACCOUNTING

    Accounting Effect:
    - Debit  Cash / Bank        (total_amount)
    - Credit Sales Revenue      (subtotal_amount)
    - Credit VAT Payable        (tax_amount)
    """

    if sale is None:
        raise ValueError("Sale object is required")

    postings: list[dict] = []

    total_amount = Decimal(sale.total_amount or "0.00")
    subtotal_amount = Decimal(sale.subtotal_amount or "0.00")
    tax_amount = Decimal(sale.tax_amount or "0.00")

    # --------------------------------------------------
    # DEBIT: CASH / BANK
    # --------------------------------------------------
    if total_amount > Decimal("0.00"):
        postings.append(
            {
                "account": get_cash_account(),
                "debit": total_amount,
                "credit": Decimal("0.00"),
            }
        )

    # --------------------------------------------------
    # CREDIT: SALES REVENUE
    # --------------------------------------------------
    if subtotal_amount > Decimal("0.00"):
        postings.append(
            {
                "account": get_sales_revenue_account(),
                "debit": Decimal("0.00"),
                "credit": subtotal_amount,
            }
        )

    # --------------------------------------------------
    # CREDIT: VAT PAYABLE
    # --------------------------------------------------
    if tax_amount > Decimal("0.00"):
        postings.append(
            {
                "account": get_vat_payable_account(),
                "debit": Decimal("0.00"),
                "credit": tax_amount,
            }
        )

    if not postings:
        raise ValueError("No accounting postings generated for POS sale")

    # --------------------------------------------------
    # DELEGATE TO POSTING ADAPTER
    # --------------------------------------------------
    return post_journal_entry(
        description="POS Sale",
        postings=postings,
        reference_type="POS_SALE",
        reference_id=str(sale.id),
    )
