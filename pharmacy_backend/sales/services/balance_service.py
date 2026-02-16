# accounting/services/balance_service.py

# accounting/services/balance_service.py

"""
BALANCE & REPORTING SERVICE (AUTHORITATIVE)

This module answers ONE question:
"What are the balances of accounts and the system?"

Responsibilities:
- Compute account balances from immutable ledger entries
- Produce trial balances
- Support reporting (P&L, Balance Sheet, Cash reports)

RULES:
- READ-ONLY: no writes, ever
- LedgerEntry is the single source of truth
- No business logic (POS, refunds, workflows)
"""

from decimal import Decimal
from django.db.models import Sum, Case, When, F
from django.db.models.functions import Coalesce

from accounting.models.account import Account
from accounting.models.ledger import LedgerEntry


# ============================================================
# DOMAIN ERRORS
# ============================================================

class BalanceServiceError(Exception):
    """Base error for balance and reporting services"""


# ============================================================
# CORE BALANCE HELPERS
# ============================================================

def get_account_balance(account: Account) -> Decimal:
    """
    Compute the balance of a single account.

    Accounting rule:
    - Assets & Expenses → Debit balance
    - Liabilities, Equity & Revenue → Credit balance
    """

    if account is None:
        raise BalanceServiceError("Account is required")

    aggregates = LedgerEntry.objects.filter(
        account=account
    ).aggregate(
        debit_total=Coalesce(
            Sum(
                Case(
                    When(entry_type=LedgerEntry.DEBIT, then=F("amount"))
                )
            ),
            Decimal("0.00"),
        ),
        credit_total=Coalesce(
            Sum(
                Case(
                    When(entry_type=LedgerEntry.CREDIT, then=F("amount"))
                )
            ),
            Decimal("0.00"),
        ),
    )

    debit = aggregates["debit_total"]
    credit = aggregates["credit_total"]

    if account.account_type in (Account.ASSET, Account.EXPENSE):
        return debit - credit

    return credit - debit


# ============================================================
# TRIAL BALANCE
# ============================================================

def get_trial_balance(chart) -> list[dict]:
    """
    Return a trial balance for a given Chart of Accounts.

    Output format:
    [
        {
            "account": Account,
            "code": str,
            "name": str,
            "account_type": str,
            "balance": Decimal,
        },
        ...
    ]
    """

    if chart is None:
        raise BalanceServiceError("Chart of Accounts is required")

    results = []

    accounts = Account.objects.filter(
        chart=chart,
        is_active=True,
    ).order_by("code")

    for account in accounts:
        balance = get_account_balance(account)

        results.append({
            "account": account,
            "code": account.code,
            "name": account.name,
            "account_type": account.account_type,
            "balance": balance,
        })

    return results


# ============================================================
# TOTALS BY ACCOUNT TYPE
# ============================================================

def get_totals_by_account_type(chart) -> dict:
    """
    Aggregate balances grouped by account type.

    Returns:
    {
        "ASSET": Decimal,
        "LIABILITY": Decimal,
        "EQUITY": Decimal,
        "REVENUE": Decimal,
        "EXPENSE": Decimal,
    }
    """

    totals = {
        Account.ASSET: Decimal("0.00"),
        Account.LIABILITY: Decimal("0.00"),
        Account.EQUITY: Decimal("0.00"),
        Account.REVENUE: Decimal("0.00"),
        Account.EXPENSE: Decimal("0.00"),
    }

    trial_balance = get_trial_balance(chart)

    for row in trial_balance:
        totals[row["account_type"]] += row["balance"]

    return totals


# ============================================================
# PROFIT & LOSS (FOUNDATION)
# ============================================================

def get_profit_and_loss(chart) -> dict:
    """
    Compute a basic Profit & Loss summary.

    Returns:
    {
        "revenue": Decimal,
        "expenses": Decimal,
        "net_profit": Decimal,
    }
    """

    totals = get_totals_by_account_type(chart)

    revenue = totals[Account.REVENUE]
    expenses = totals[Account.EXPENSE]

    return {
        "revenue": revenue,
        "expenses": expenses,
        "net_profit": revenue - expenses,
    }
