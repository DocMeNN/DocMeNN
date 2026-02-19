"""
PATH: accounting/api/views/trial_balance.py

TRIAL BALANCE API VIEW (READ-ONLY)

Phase 5 Hardening:
- Permission-gated: requires accounting.view_ledgerentry
- Chart isolation: users cannot query arbitrary chart_id unless superuser
  (or they have explicit permission to view charts).
"""

from __future__ import annotations

from datetime import datetime, time

from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounting.models.chart import ChartOfAccounts
from accounting.services.account_resolver import get_active_chart
from accounting.services.trial_balance_service import TrialBalanceService


def _as_aware_dt(dt):
    if dt is None:
        return None
    if timezone.is_naive(dt):
        return timezone.make_aware(dt, timezone.get_current_timezone())
    return dt


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
            name="as_of",
            type=str,
            location=OpenApiParameter.QUERY,
            required=False,
            description="ISO datetime snapshot (e.g. 2026-01-15T23:59:59).",
        ),
        OpenApiParameter(
            name="as_of_date",
            type=str,
            location=OpenApiParameter.QUERY,
            required=False,
            description="Convenience alias for end-of-day snapshot (YYYY-MM-DD). If set, overrides as_of.",
        ),
    ],
    responses={200: dict},
)
class TrialBalanceView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # ✅ Permission hardening (matrix: Trial Balance -> accounting.view_ledgerentry)
        if not request.user.has_perm("accounting.view_ledgerentry"):
            return Response(
                {"detail": "You do not have permission to view trial balance."},
                status=status.HTTP_403_FORBIDDEN,
            )

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

            # ✅ Chart isolation: prevent cross-chart leakage unless explicitly allowed
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

        as_of_param = request.query_params.get("as_of")
        as_of_date_param = request.query_params.get("as_of_date")

        as_of = None

        if as_of_date_param:
            d = parse_date(str(as_of_date_param).strip())
            if d is None:
                return Response(
                    {"detail": "Invalid as_of_date (expected YYYY-MM-DD)"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            # End-of-day snapshot
            as_of = _as_aware_dt(datetime.combine(d, time.max.replace(microsecond=0)))
        elif as_of_param is not None:
            raw = str(as_of_param).strip()
            if raw == "":
                as_of = None
            else:
                dt = parse_datetime(raw)
                if dt is None:
                    return Response(
                        {"detail": "Invalid as_of (expected ISO datetime)"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                as_of = _as_aware_dt(dt)

        service = TrialBalanceService()
        data = service.generate(chart=chart, as_of=as_of)

        data["chart"] = {
            "id": chart.id,
            "name": chart.name,
            "is_active": chart.is_active,
        }
        data["as_of_date"] = as_of_date_param or None

        return Response(data, status=status.HTTP_200_OK)
