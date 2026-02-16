# accounting/api/views/__init__.py

"""
accounting.api.views package

Expose public API views cleanly without making routing/imports fragile.

Important:
- ViewSets are defined in accounting.api.view (singular) in this codebase.
- Do NOT import accounting.api.urls from here to avoid circular imports.
"""

# ViewSets
from accounting.api.view import JournalEntryViewSet, LedgerEntryViewSet

# Read-only reports
from accounting.api.views.trial_balance import TrialBalanceView
from accounting.api.views.balance_sheet import BalanceSheetView
from accounting.api.views.profit_and_loss import ProfitAndLossView
from accounting.api.views.overview import AccountingOverviewView

# Posting actions / master data
from accounting.api.views.opening_balances import OpeningBalancesCreateView
from accounting.api.views.expenses import ExpenseListCreateView
from accounting.api.views.close_period import ClosePeriodView
from accounting.api.views.accounts import ActiveChartAccountsView

__all__ = [
    "JournalEntryViewSet",
    "LedgerEntryViewSet",
    "TrialBalanceView",
    "BalanceSheetView",
    "ProfitAndLossView",
    "AccountingOverviewView",
    "OpeningBalancesCreateView",
    "ExpenseListCreateView",
    "ClosePeriodView",
    "ActiveChartAccountsView",
]
