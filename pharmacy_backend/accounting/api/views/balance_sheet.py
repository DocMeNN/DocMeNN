# PATH: accounting/api/views/balance_sheet.py

"""
PATH: accounting/api/views/balance_sheet.py

BALANCE SHEET API VIEW

Read-only endpoint exposing the balance sheet snapshot.
Chart-aware + posted_at timeline enforced by the service.

Phase 5 Hardening:
- Permission-gated: requires accounting.view_ledgerentry
- Chart isolation: users cannot query arbitrary chart_id unless superuser
  (or they have explicit permission to view charts).
"""

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounting.models.chart import ChartOfAccounts
from accounting.services.account_resolver import get_active_chart
from accounting.services.balance_sheet_service import generate_balance_sheet
from accounting.services.exceptions import AccountingServiceError


class BalanceSheetView(APIView):
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
                type=OpenApiTypes.DATE,
                required=False,
                description="Optional cutoff date (YYYY-MM-DD), inclusive end-of-day.",
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
        as_of_date = request.query_params.get("as_of_date")

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

        try:
            balance_sheet = generate_balance_sheet(chart=chart, as_of_date=as_of_date)
        except AccountingServiceError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        balance_sheet["chart"] = {
            "id": chart.id,
            "name": chart.name,
            "is_active": chart.is_active,
        }
        balance_sheet["as_of_date"] = as_of_date or None

        return Response(balance_sheet, status=status.HTTP_200_OK)
