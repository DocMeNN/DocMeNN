# sales/views/reports.py

"""
PATH: sales/views/reports.py

POS REPORTS (AUTHORITATIVE OPERATIONAL REPORTS)

Fixes included:
- Refund reporting now filters by SaleRefundAudit.refunded_at (refund event time),
  NOT by sale.completed_at (sale event time).
  This fixes the bug where refunds done today for a sale completed earlier
  would show as 0 in Daily Sales and Z-Report.

- Refund totals are computed best-effort to support partial refunds:
  prefer any explicit refunded amount fields if present, otherwise fallback
  to original_total_amount.

Notes:
- Gross numbers are still based on COMPLETED sales within day bounds.
- Refunds are based on audit events within day bounds.
"""

from __future__ import annotations

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


def _refund_amount_from_audit(audit: SaleRefundAudit) -> Decimal:
    """
    Best-effort refund amount resolver.

    Prefer partial/refund amount fields if present.
    Fallback to original_total_amount.
    """
    candidate_fields = [
        "refund_total_amount",
        "refunded_total_amount",
        "refund_amount",
        "refunded_amount",
        "total_refunded_amount",
        "partial_refund_total_amount",
    ]

    for attr in candidate_fields:
        if hasattr(audit, attr):
            v = getattr(audit, attr, None)
            if v is not None:
                return Decimal(str(v))

    return Decimal(str(getattr(audit, "original_total_amount", 0) or 0))


class DailySalesReportView(APIView):
    """
    Daily Sales Report (authoritative summary)
    Includes:
    - gross sales (completed)
    - refunds (refunded via audit events)
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

        # Gross completed totals
        gross = completed_qs.aggregate(
            sale_count=Count("id"),
            subtotal=Sum("subtotal_amount"),
            tax=Sum("tax_amount"),
            discount=Sum("discount_amount"),
            total=Sum("total_amount"),
        )

        gross_total = gross.get("total") or Decimal("0.00")

        # Refund totals MUST be based on refund event time
        refunds_qs = SaleRefundAudit.objects.filter(
            refunded_at__gte=start,
            refunded_at__lt=end,
        )

        refund_events_count = refunds_qs.count()
        refund_total = Decimal("0.00")
        refunded_sale_ids = set()

        for a in refunds_qs.iterator():
            refund_total += _refund_amount_from_audit(a)
            sid = getattr(a, "sale_id", None)
            if sid is not None:
                refunded_sale_ids.add(sid)

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
                    # more accurate than relying on Sale.STATUS_REFUNDED
                    "refunded_sales_count": len(refunded_sale_ids),
                    "refund_events_count": refund_events_count,
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

        # Refund totals MUST be based on refund event time
        refunds_qs = SaleRefundAudit.objects.filter(
            refunded_at__gte=start,
            refunded_at__lt=end,
        )

        refunds_total = Decimal("0.00")
        for a in refunds_qs.iterator():
            refunds_total += _refund_amount_from_audit(a)

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