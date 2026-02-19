# sales/views/reports.py

from datetime import datetime, time, timedelta
from decimal import Decimal

from django.db.models import Count, Sum
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from permissions.roles import CAP_REPORTS_VIEW_POS, HasCapability
from sales.models.refund_audit import SaleRefundAudit
from sales.models.sale import Sale


def _parse_report_date(date_str: str | None):
    """
    Accepts YYYY-MM-DD.
    Defaults to today (server timezone).
    """
    if not date_str:
        return timezone.localdate()

    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return None


def _day_bounds(d):
    """
    Returns timezone-aware datetime bounds [start, end) for a local date.
    """
    tz = timezone.get_current_timezone()
    start = timezone.make_aware(datetime.combine(d, time.min), tz)
    end = start + timedelta(days=1)
    return start, end


def _money(x) -> str:
    """
    JSON-safe money string.
    """
    if x is None:
        return "0.00"
    if isinstance(x, Decimal):
        return f"{x:.2f}"
    return f"{Decimal(str(x)):.2f}"


def _display_name(
    email: str | None, first_name: str | None, last_name: str | None
) -> str:
    """
    Best-effort display label for cashier.
    """
    fn = (first_name or "").strip()
    ln = (last_name or "").strip()
    full = f"{fn} {ln}".strip()

    if full:
        return full
    if email:
        return email
    return "Unknown"


class DailySalesReportView(APIView):
    """
    Daily Sales Report (authoritative summary)
    Includes:
    - gross sales (completed)
    - refunds (refunded via audit snapshot)
    - net sales
    - payment breakdown
    - cashier breakdown
    """

    permission_classes = [IsAuthenticated, HasCapability]
    required_capability = CAP_REPORTS_VIEW_POS

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="date",
                type=OpenApiTypes.DATE,
                required=False,
                description="Report date in YYYY-MM-DD. Defaults to today (server timezone).",
            )
        ],
        description="Daily sales summary + payment breakdown + cashier breakdown.",
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request):
        d = _parse_report_date(request.query_params.get("date"))
        if d is None:
            return Response(
                {"detail": "Invalid date format. Use YYYY-MM-DD."},
                status=400,
            )

        start, end = _day_bounds(d)

        completed_qs = Sale.objects.filter(
            status=Sale.STATUS_COMPLETED,
            completed_at__gte=start,
            completed_at__lt=end,
        )

        refunded_qs = Sale.objects.filter(
            status=Sale.STATUS_REFUNDED,
            completed_at__gte=start,
            completed_at__lt=end,
        )

        # Gross completed totals
        gross = completed_qs.aggregate(
            sale_count=Count("id"),
            subtotal=Sum("subtotal_amount"),
            tax=Sum("tax_amount"),
            discount=Sum("discount_amount"),
            total=Sum("total_amount"),
        )

        # Refund totals (prefer audit snapshot)
        refunds = SaleRefundAudit.objects.filter(
            sale__completed_at__gte=start,
            sale__completed_at__lt=end,
        ).aggregate(
            refund_count=Count("id"),
            refund_total=Sum("original_total_amount"),
        )

        gross_total = gross.get("total") or Decimal("0.00")
        refund_total = refunds.get("refund_total") or Decimal("0.00")
        net_total = gross_total - refund_total

        # Payment breakdown (completed only)
        payment_breakdown = list(
            completed_qs.values("payment_method")
            .annotate(count=Count("id"), total=Sum("total_amount"))
            .order_by("payment_method")
        )

        # Cashier breakdown (completed only)
        cashier_rows = list(
            completed_qs.values(
                "user__id",
                "user__email",
                "user__first_name",
                "user__last_name",
            )
            .annotate(count=Count("id"), total=Sum("total_amount"))
            .order_by("user__email")
        )

        refunded_count = refunded_qs.count()

        return Response(
            {
                "date": str(d),
                "gross": {
                    "sales_count": gross.get("sale_count") or 0,
                    "subtotal_amount": _money(gross.get("subtotal")),
                    "tax_amount": _money(gross.get("tax")),
                    "discount_amount": _money(gross.get("discount")),
                    "total_amount": _money(gross_total),
                },
                "refunds": {
                    "refunded_sales_count": refunded_count,
                    "refund_events_count": refunds.get("refund_count") or 0,
                    "refund_total_amount": _money(refund_total),
                },
                "net": {
                    "net_total_amount": _money(net_total),
                },
                "breakdowns": {
                    "by_payment_method": [
                        {
                            "payment_method": row["payment_method"],
                            "count": row["count"],
                            "total_amount": _money(row["total"]),
                        }
                        for row in payment_breakdown
                    ],
                    "by_cashier": [
                        {
                            "user_id": row["user__id"],
                            "email": row["user__email"],
                            "display_name": _display_name(
                                row.get("user__email"),
                                row.get("user__first_name"),
                                row.get("user__last_name"),
                            ),
                            "count": row["count"],
                            "total_amount": _money(row["total"]),
                        }
                        for row in cashier_rows
                    ],
                },
            }
        )


class CashReconciliationReportView(APIView):
    """
    Cash vs Non-cash reconciliation view for a day.
    """

    permission_classes = [IsAuthenticated, HasCapability]
    required_capability = CAP_REPORTS_VIEW_POS

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="date",
                type=OpenApiTypes.DATE,
                required=False,
                description="Report date in YYYY-MM-DD. Defaults to today.",
            )
        ],
        description="Cash vs non-cash totals for the day (completed sales).",
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request):
        d = _parse_report_date(request.query_params.get("date"))
        if d is None:
            return Response(
                {"detail": "Invalid date format. Use YYYY-MM-DD."}, status=400
            )

        start, end = _day_bounds(d)

        qs = Sale.objects.filter(
            status=Sale.STATUS_COMPLETED,
            completed_at__gte=start,
            completed_at__lt=end,
        )

        cash_total = qs.filter(payment_method__iexact="cash").aggregate(
            total=Sum("total_amount")
        ).get("total") or Decimal("0.00")

        non_cash_total = qs.exclude(payment_method__iexact="cash").aggregate(
            total=Sum("total_amount")
        ).get("total") or Decimal("0.00")

        breakdown = list(
            qs.values("payment_method")
            .annotate(count=Count("id"), total=Sum("total_amount"))
            .order_by("payment_method")
        )

        return Response(
            {
                "date": str(d),
                "cash_total_amount": _money(cash_total),
                "non_cash_total_amount": _money(non_cash_total),
                "by_payment_method": [
                    {
                        "payment_method": row["payment_method"],
                        "count": row["count"],
                        "total_amount": _money(row["total"]),
                    }
                    for row in breakdown
                ],
            }
        )


class ZReportView(APIView):
    """
    Z-Report / Daily close snapshot.
    Later we can extend this to cashier shifts (session-based Z reports).
    """

    permission_classes = [IsAuthenticated, HasCapability]
    required_capability = CAP_REPORTS_VIEW_POS

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="date",
                type=OpenApiTypes.DATE,
                required=False,
                description="Report date in YYYY-MM-DD. Defaults to today.",
            )
        ],
        description="Z-Report snapshot (daily close summary).",
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request):
        d = _parse_report_date(request.query_params.get("date"))
        if d is None:
            return Response(
                {"detail": "Invalid date format. Use YYYY-MM-DD."}, status=400
            )

        start, end = _day_bounds(d)

        completed_qs = Sale.objects.filter(
            status=Sale.STATUS_COMPLETED,
            completed_at__gte=start,
            completed_at__lt=end,
        )

        gross_total = completed_qs.aggregate(total=Sum("total_amount")).get(
            "total"
        ) or Decimal("0.00")
        tx_count = completed_qs.count()

        refunds_total = SaleRefundAudit.objects.filter(
            sale__completed_at__gte=start,
            sale__completed_at__lt=end,
        ).aggregate(total=Sum("original_total_amount")).get("total") or Decimal("0.00")

        return Response(
            {
                "date": str(d),
                "z_report": {
                    "transaction_count": tx_count,
                    "gross_total_amount": _money(gross_total),
                    "refund_total_amount": _money(refunds_total),
                    "net_total_amount": _money(gross_total - refunds_total),
                },
                "generated_at": timezone.now().isoformat(),
            }
        )
