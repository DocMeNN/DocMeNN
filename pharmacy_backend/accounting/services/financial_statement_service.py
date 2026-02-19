# accounting/services/financial_statement_service.py

"""
FINANCIAL STATEMENT SERVICE (AUTHORITATIVE)

This module produces formal financial statements from the ledger.

Statements supported:
- Balance Sheet
- Profit & Loss (Income Statement)

RULES:
- READ-ONLY (never writes)
- LedgerEntry is the single source of truth
- Must enforce accounting equations
- No POS logic
- No posting logic
"""

from decimal import Decimal

from accounting.models.account import Account
from accounting.services.balance_service import (
    get_trial_balance,
)

# ============================================================
# DOMAIN ERRORS
# ============================================================


class FinancialStatementError(Exception):
    """Raised when financial statements are structurally invalid"""


# ============================================================
# BALANCE SHEET
# ============================================================


def get_balance_sheet(chart) -> dict:
    """
    Produce a Balance Sheet.

    Accounting Equation (MUST HOLD):
        Assets = Liabilities + Equity

    Returns:
    {
        "assets": {
            "accounts": [...],
            "total": Decimal,
        },
        "liabilities": {
            "accounts": [...],
            "total": Decimal,
        },
        "equity": {
            "accounts": [...],
            "total": Decimal,
        },
        "is_balanced": bool,
    }
    """

    if chart is None:
        raise FinancialStatementError("Chart of Accounts is required")

    trial_balance = get_trial_balance(chart)

    assets = []
    liabilities = []
    equity = []

    total_assets = Decimal("0.00")
    total_liabilities = Decimal("0.00")
    total_equity = Decimal("0.00")

    for row in trial_balance:
        account_type = row["account_type"]
        balance = row["balance"]

        if account_type == Account.ASSET:
            assets.append(row)
            total_assets += balance

        elif account_type == Account.LIABILITY:
            liabilities.append(row)
            total_liabilities += balance

        elif account_type == Account.EQUITY:
            equity.append(row)
            total_equity += balance

    is_balanced = total_assets == (total_liabilities + total_equity)

    return {
        "assets": {
            "accounts": assets,
            "total": total_assets,
        },
        "liabilities": {
            "accounts": liabilities,
            "total": total_liabilities,
        },
        "equity": {
            "accounts": equity,
            "total": total_equity,
        },
        "is_balanced": is_balanced,
    }


# ============================================================
# PROFIT & LOSS (INCOME STATEMENT)
# ============================================================


def get_income_statement(chart) -> dict:
    """
    Produce an Income Statement (Profit & Loss).

    Returns:
    {
        "revenue": {
            "accounts": [...],
            "total": Decimal,
        },
        "expenses": {
            "accounts": [...],
            "total": Decimal,
        },
        "net_profit": Decimal,
    }
    """

    if chart is None:
        raise FinancialStatementError("Chart of Accounts is required")

    trial_balance = get_trial_balance(chart)

    revenue_accounts = []
    expense_accounts = []

    total_revenue = Decimal("0.00")
    total_expenses = Decimal("0.00")

    for row in trial_balance:
        account_type = row["account_type"]
        balance = row["balance"]

        if account_type == Account.REVENUE:
            revenue_accounts.append(row)
            total_revenue += balance

        elif account_type == Account.EXPENSE:
            expense_accounts.append(row)
            total_expenses += balance

    return {
        "revenue": {
            "accounts": revenue_accounts,
            "total": total_revenue,
        },
        "expenses": {
            "accounts": expense_accounts,
            "total": total_expenses,
        },
        "net_profit": total_revenue - total_expenses,
    }


# ============================================================
# VALIDATION / HEALTH CHECK
# ============================================================


def validate_financials(chart) -> None:
    """
    Hard validation of financial integrity.

    Raises FinancialStatementError if:
    - Balance Sheet does not balance
    """

    balance_sheet = get_balance_sheet(chart)

    if not balance_sheet["is_balanced"]:
        raise FinancialStatementError(
            "Balance Sheet is NOT balanced: "
            f"Assets={balance_sheet['assets']['total']} "
            f"Liabilities+Equity="
            f"{balance_sheet['liabilities']['total'] + balance_sheet['equity']['total']}"
        )
