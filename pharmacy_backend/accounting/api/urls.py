# accounting/api/urls.py

from django.urls import include, path
from rest_framework.routers import DefaultRouter

# Canonical ViewSets live in accounting/api/view.py (singular) in this project.
# We import directly to avoid circular imports through views/__init__.py.
from accounting.api.view import JournalEntryViewSet, LedgerEntryViewSet
from accounting.api.views.accounts import ActiveChartAccountsView
from accounting.api.views.balance_sheet import BalanceSheetView
from accounting.api.views.close_period import ClosePeriodView
from accounting.api.views.expenses import ExpenseListCreateView
from accounting.api.views.opening_balances import OpeningBalancesCreateView
from accounting.api.views.overview import AccountingOverviewView
from accounting.api.views.profit_and_loss import ProfitAndLossView
from accounting.api.views.trial_balance import TrialBalanceView

router = DefaultRouter()
router.register("journal-entries", JournalEntryViewSet, basename="journal-entry")
router.register("ledger-entries", LedgerEntryViewSet, basename="ledger-entry")

urlpatterns = [
    # Router endpoints
    path("", include(router.urls)),
    # Reports
    path("trial-balance/", TrialBalanceView.as_view(), name="trial-balance"),
    path("balance-sheet/", BalanceSheetView.as_view(), name="balance-sheet"),
    path("profit-and-loss/", ProfitAndLossView.as_view(), name="profit-and-loss"),
    path("overview/", AccountingOverviewView.as_view(), name="accounting-overview"),
    # Master data (read-only, chart-aware)
    path("accounts/", ActiveChartAccountsView.as_view(), name="accounts"),
    # Posting actions
    path(
        "opening-balances/",
        OpeningBalancesCreateView.as_view(),
        name="opening-balances",
    ),
    path("expenses/", ExpenseListCreateView.as_view(), name="expenses"),
    path("close-period/", ClosePeriodView.as_view(), name="close-period"),
]
