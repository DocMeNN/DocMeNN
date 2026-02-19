# accounting/api/views/overview.py

"""
PATH: accounting/api/views/overview.py

ACCOUNTING OVERVIEW DASHBOARD (KPIs)

Read-only, computed live from immutable ledger.

Phase 5 Hardening:
- Permission-gated: requires accounting.view_ledgerentry
- Chart isolation: users cannot query arbitrary chart_id unless superuser
  (or they have explicit permission to view charts).
"""

from __future__ import annotations

from datetime import datetime, time

from django.utils import timezone
from django.utils.dateparse import parse_date
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounting.models.chart import ChartOfAccounts
from accounting.models.period_close import PeriodClose
from accounting.services.account_resolver import get_active_chart
from accounting.services.balance_service import get_totals_by_account_type
from accounting.services.profit_and_loss_service import get_profit_and_loss


def _as_float(v, default=0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return float(default)


def _pick_key(d: dict, *keys, default=0):
    if not isinstance(d, dict):
        return default
    for k in keys:
        if k in d:
            return d.get(k)
    return default


def _end_of_day_aware(d) -> datetime:
    naive = datetime.combine(d, time(23, 59, 59))
    if timezone.is_naive(naive):
        return timezone.make_aware(naive, timezone.get_current_timezone())
    return naive


def _is_balanced(assets: float, liabilities: float, equity: float) -> bool:
    return round(assets, 2) == round(liabilities + equity, 2)


class AccountingOverviewView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["accounting"],
        parameters=[
            OpenApiParameter(
                name="chart_id",
                type=int,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Optional Chart of Accounts ID. If omitted, active chart is used.",
            ),
            OpenApiParameter(
                name="as_of_date",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Optional snapshot date (YYYY-MM-DD). If provided, KPIs are computed up to end-of-day.",
            ),
        ],
        responses={200: dict},
    )
    def get(self, request, *args, **kwargs):
        # ✅ Permission hardening
        if not request.user.has_perm("accounting.view_ledgerentry"):
            return Response(
                {"detail": "You do not have permission to view financial reports."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # ----------------------------
        # CHART RESOLUTION + ISOLATION
        # ----------------------------
        chart_id = request.query_params.get("chart_id")
        active_chart = get_active_chart()

        if chart_id:
            try:
                requested_chart_id = int(chart_id)
            except (ValueError, TypeError):
                return Response(
                    {"detail": "chart_id must be an integer"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if requested_chart_id != active_chart.id:
                if not (
                    request.user.is_superuser
                    or request.user.has_perm("accounting.view_chartofaccounts")
                ):
                    return Response(
                        {"detail": "You are not allowed to view this chart."},
                        status=status.HTTP_403_FORBIDDEN,
                    )

            try:
                chart = ChartOfAccounts.objects.get(id=requested_chart_id)
            except ChartOfAccounts.DoesNotExist:
                return Response(
                    {"detail": "Chart not found for given chart_id"},
                    status=status.HTTP_404_NOT_FOUND,
                )
        else:
            chart = active_chart

        # ----------------------------
        # OPTIONAL AS-OF SNAPSHOT DATE
        # ----------------------------
        as_of_raw = request.query_params.get("as_of_date")
        as_of_date = None
        as_of_dt = None

        if as_of_raw:
            d = parse_date(str(as_of_raw).strip())
            if d is None:
                return Response(
                    {"detail": "Invalid as_of_date format. Use YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            as_of_date = d
            as_of_dt = _end_of_day_aware(d)

        lock_check_date = as_of_date or timezone.localdate()

        # ----------------------------
        # PERIOD CLOSE / LOCK STATUS
        # ----------------------------
        last_close = (
            PeriodClose.objects.filter(chart=chart)
            .select_related("journal_entry")
            .order_by("-end_date", "-created_at")
            .first()
        )

        locking_close = (
            PeriodClose.objects.filter(
                chart=chart,
                start_date__lte=lock_check_date,
                end_date__gte=lock_check_date,
            )
            .select_related("journal_entry")
            .order_by("-end_date", "-created_at")
            .first()
        )

        period_locked = locking_close is not None

        # ----------------------------
        # COMPUTE BALANCE TOTALS (CHART + AS-OF AWARE)
        # ----------------------------
        try:
            totals = get_totals_by_account_type(chart=chart, as_of=as_of_dt)
        except TypeError:
            # Older signature fallback
            try:
                totals = get_totals_by_account_type(chart)
            except TypeError:
                totals = get_totals_by_account_type()

        assets = _pick_key(totals, "ASSET", "assets", "asset", default=0)
        liabilities = _pick_key(
            totals, "LIABILITY", "liabilities", "liability", default=0
        )
        equity = _pick_key(totals, "EQUITY", "equity", default=0)

        assets_n = _as_float(assets, 0)
        liabilities_n = _as_float(liabilities, 0)
        equity_n = _as_float(equity, 0)

        # ----------------------------
        # P&L KPI (OPTIONALLY AS-OF)
        # ----------------------------
        try:
            pnl = get_profit_and_loss(chart=chart, start_date=None, end_date=as_of_dt)
        except TypeError:
            pnl = get_profit_and_loss(start_date=None, end_date=as_of_dt)

        income_n = _as_float(pnl.get("income"), 0)
        expenses_n = _as_float(pnl.get("expenses"), 0)
        net_profit_n = _as_float(pnl.get("net_profit"), 0)

        balanced = _is_balanced(assets_n, liabilities_n, equity_n)

        def _je_payload(pc):
            if not pc:
                return None
            je = pc.journal_entry
            return {
                "start_date": pc.start_date.isoformat(),
                "end_date": pc.end_date.isoformat(),
                "closed_at": pc.created_at.isoformat(),
                "journal_entry": {
                    "id": str(je.id),
                    "reference": je.reference,
                    "posted_at": je.posted_at.isoformat() if je.posted_at else None,
                },
            }

        payload = {
            "chart": {"id": chart.id, "name": chart.name, "is_active": chart.is_active},
            "as_of_date": as_of_raw or None,
            "assets": assets_n,
            "liabilities": liabilities_n,
            "equity": equity_n,
            "balanced": balanced,
            "income": income_n,
            "expenses": expenses_n,
            "net_profit": net_profit_n,
            "period_status": {
                "check_date": lock_check_date.isoformat(),
                "locked": period_locked,
                "locked_period": _je_payload(locking_close),
                "last_close": _je_payload(last_close),
            },
        }

        return Response(payload, status=status.HTTP_200_OK)
