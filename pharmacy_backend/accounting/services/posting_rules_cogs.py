# accounting/services/posting_rules_cogs.py

"""
POSTING RULES — COST OF GOODS SOLD (COGS)

This module defines the authoritative accounting rules
for recognizing Cost of Goods Sold when inventory is sold.

Responsibilities:
- Define WHICH accounts are debited and credited
- Enforce accounting correctness
- Remain calculation-agnostic (amount is passed in)

This module:
- DOES NOT save journal entries
- DOES NOT touch inventory quantities
- DOES NOT calculate costs
"""

from decimal import Decimal

from accounting.services.account_resolver import (
    get_active_chart,
    AccountResolutionError,
)
from accounting.models.account import Account


# ============================================================
# DOMAIN ERRORS
# ============================================================

class COGSPostingError(Exception):
    """Raised when COGS posting rules cannot be resolved"""


# ============================================================
# ACCOUNT RESOLUTION
# ============================================================

def get_cogs_expense_account() -> Account:
    """
    Expense account for Cost of Goods Sold.
    """
    chart = get_active_chart()

    try:
        return Account.objects.get(
            chart=chart,
            code="5000",  # 🔑 Cost of Goods Sold
        )
    except Account.DoesNotExist:
        raise COGSPostingError(
            "COGS expense account (code=5000) not found in active chart"
        )


def get_inventory_asset_account() -> Account:
    """
    Asset account representing inventory on hand.
    """
    chart = get_active_chart()

    try:
        return Account.objects.get(
            chart=chart,
            code="1200",  # 🔑 Inventory Asset
        )
    except Account.DoesNotExist:
        raise COGSPostingError(
            "Inventory asset account (code=1200) not found in active chart"
        )


# ============================================================
# POSTING RULE
# ============================================================

def build_cogs_posting(amount: Decimal) -> list[dict]:
    """
    Build the accounting postings for Cost of Goods Sold.

    Accounting rule:
    - Debit  COGS Expense
    - Credit Inventory Asset

    Args:
        amount (Decimal): Cost value of inventory sold

    Returns:
        List of posting instructions (debit / credit)

    Example output:
    [
        {"account": <Account>, "debit": 500, "credit": 0},
        {"account": <Account>, "debit": 0, "credit": 500},
    ]
    """

    if amount <= 0:
        raise COGSPostingError("COGS amount must be greater than zero")

    cogs_account = get_cogs_expense_account()
    inventory_account = get_inventory_asset_account()

    return [
        {
            "account": cogs_account,
            "debit": amount,
            "credit": Decimal("0.00"),
        },
        {
            "account": inventory_account,
            "debit": Decimal("0.00"),
            "credit": amount,
        },
    ]
