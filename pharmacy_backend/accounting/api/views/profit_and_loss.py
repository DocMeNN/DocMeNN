# PATH: accounting/api/views/profit_and_loss.py


"""
PATH: accounting/api/views/profit_and_loss.py

PROFIT & LOSS (P&L) API VIEW

Read-only endpoint exposing a profit & loss snapshot over a date range.
Chart-aware + posted_at timeline enforced by the service.

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
from accounting.services.exceptions import AccountingServiceError
from accounting.services.profit_and_loss_service import get_profit_and_loss


def _as_aware_dt(dt: datetime) -> datetime:
    if timezone.is_naive(dt):
        return timezone.make_aware(dt, timezone.get_current_timezone())
    return dt


def _parse_date_or_datetime(value: str | None, field_name: str):
    if value is None:
        return None

    s = str(value).strip()
    if s == "":
        return None

    dt = parse_datetime(s)
    if dt is not None:
        return dt

    d = parse_date(s)
    if d is not None:
        return d

    raise ValueError(f"Invalid {field_name} (expected YYYY-MM-DD or ISO datetime)")


class ProfitAndLossView(APIView):
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
                name="start_date",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description="YYYY-MM-DD or ISO datetime. Filters JournalEntry.posted_at >= start_date.",
            ),
            OpenApiParameter(
                name="end_date",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description="YYYY-MM-DD or ISO datetime. Filters JournalEntry.posted_at <= end_date.",
            ),
            OpenApiParameter(
                name="as_of_date",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Convenience alias for end-of-day snapshot (YYYY-MM-DD). If set, overrides end_date.",
            ),
        ],
        responses={200: dict},
    )
    def get(self, request):
        if not request.user.has_perm("accounting.view_ledgerentry"):
            return Response(
                {"detail": "You do not have permission to view financial reports."},
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

        start_raw = request.query_params.get("start_date")
        end_raw = request.query_params.get("end_date")
        as_of_raw = request.query_params.get("as_of_date")

        try:
            start_parsed = _parse_date_or_datetime(start_raw, "start_date")
            end_parsed = _parse_date_or_datetime(end_raw, "end_date")
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        if as_of_raw:
            d = parse_date(str(as_of_raw).strip())
            if d is None:
                return Response(
                    {"detail": "Invalid as_of_date format. Use YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            end_parsed = d

        start_dt = None
        if start_parsed is not None:
            if isinstance(start_parsed, datetime):
                start_dt = _as_aware_dt(start_parsed)
            else:
                start_dt = _as_aware_dt(datetime.combine(start_parsed, time.min))

        end_dt = None
        if end_parsed is not None:
            if isinstance(end_parsed, datetime):
                end_dt = _as_aware_dt(end_parsed)
            else:
                end_dt = _as_aware_dt(
                    datetime.combine(end_parsed, time.max.replace(microsecond=0))
                )

        if start_dt and end_dt and start_dt > end_dt:
            return Response(
                {"detail": "start_date cannot be after end_date"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            data = get_profit_and_loss(
                chart=chart, start_date=start_dt, end_date=end_dt
            )

            data["chart"] = {
                "id": chart.id,
                "name": chart.name,
                "is_active": chart.is_active,
            }
            data["period"] = {
                "start_date": start_dt.isoformat() if start_dt else None,
                "end_date": end_dt.isoformat() if end_dt else None,
                "as_of_date": as_of_raw or None,
            }

            return Response(data, status=status.HTTP_200_OK)

        except AccountingServiceError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
