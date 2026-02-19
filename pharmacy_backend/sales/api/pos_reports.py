# sales/api/pos_reports.py

"""
POS REPORTS (SALES MODULE)

PATH: sales/api/pos_reports.py

Purpose:
- Provide operational POS reports for Admin UI.
- Daily Sales, Cash Reconciliation, Z-Report.

Contract:
- date is optional, defaults to today (server timezone).
- date format: YYYY-MM-DD

Definitions:
- Sales for the day:
  Prefer completed_at in [start, end), else fallback to created_at.
- Refund totals for the day:
  Uses SaleRefundAudit.refunded_at in [start, end).
  Partial refunds are supported best-effort via common amount fields if present;
  otherwise falls back to original_total_amount.

Security:
- Admin-only
"""

from __future__ import annotations

from datetime import date as date_cls

from django.db.models import Count, Sum
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from sales.models import Sale
from sales.models.refund_audit import SaleRefundAudit

try:
    from sales.models.sale_payment_allocation import SalePaymentAllocation
except Exception:
    SalePaymentAllocation = None


class _AdminOnly(IsAuthenticated):
    def has_permission(self, request, view):
        ok = super().has_permission(request, view)
        if not ok:
            return False
        role = getattr(request.user, "role", None)
        return role == "admin"


def _parse_date(date_str: str | None) -> date_cls:
    if date_str:
        try:
            yyyy, mm, dd = [int(x) for x in str(date_str).split("-")]
            return date_cls(yyyy, mm, dd)
        except Exception:
            return timezone.localdate()
    return timezone.localdate()


def _date_bounds(day: date_cls):
    tz = timezone.get_current_timezone()
    start = timezone.make_aware(
        timezone.datetime(day.year, day.month, day.day, 0, 0, 0), tz
    )
    end = start + timezone.timedelta(days=1)
    return start, end


def _sum_money(value):
    return float(value or 0)


def _refund_amount_from_audit(audit: SaleRefundAudit) -> float:
    """
    Best-effort:
    - Prefer partial refund amount fields if present.
    - Fallback to original_total_amount.
    """
    for attr in [
        "refund_total_amount",
        "refunded_total_amount",
        "refund_amount",
        "refunded_amount",
        "total_refunded_amount",
        "partial_refund_total_amount",
    ]:
        if hasattr(audit, attr):
            v = getattr(audit, attr)
            if v is not None:
                return _sum_money(v)

    return _sum_money(getattr(audit, "original_total_amount", 0))


def _sales_for_day(day: date_cls):
    start, end = _date_bounds(day)

    # Prefer completed_at for "real sales date"
    qs = Sale.objects.filter(completed_at__gte=start, completed_at__lt=end)
    if not qs.exists():
        qs = Sale.objects.filter(created_at__gte=start, created_at__lt=end)

    return qs, start, end


class DailySalesReportView(APIView):
    permission_classes = [_AdminOnly]

    def get(self, request):
        day = _parse_date(request.query_params.get("date"))
        sales_qs, start, end = _sales_for_day(day)

        gross = sales_qs.aggregate(
            sales_count=Count("id"),
            total_amount=Sum("total_amount"),
        )

        refunds_qs = SaleRefundAudit.objects.filter(
            refunded_at__gte=start, refunded_at__lt=end
        )
        refund_count = refunds_qs.count()
        refund_total = sum(_refund_amount_from_audit(a) for a in refunds_qs.iterator())

        by_payment_method = list(
            sales_qs.values("payment_method")
            .annotate(count=Count("id"), total_amount=Sum("total_amount"))
            .order_by("payment_method")
        )

        by_cashier_raw = list(
            sales_qs.values("user")
            .annotate(count=Count("id"), total_amount=Sum("total_amount"))
            .order_by("-total_amount")
        )

        cashier_user_ids = [r["user"] for r in by_cashier_raw if r.get("user")]
        user_map = {}
        if cashier_user_ids:
            User = Sale._meta.get_field("user").remote_field.model
            for u in User.objects.filter(id__in=cashier_user_ids):
                display = ""
                try:
                    display = u.get_full_name() or ""
                except Exception:
                    display = ""
                user_map[str(u.id)] = {
                    "display_name": display or getattr(u, "username", None),
                    "email": getattr(u, "email", None),
                }

        by_cashier = []
        for r in by_cashier_raw:
            uid = str(r.get("user") or "")
            meta = user_map.get(uid, {})
            by_cashier.append(
                {
                    "user_id": r.get("user"),
                    "display_name": meta.get("display_name"),
                    "email": meta.get("email"),
                    "count": r.get("count") or 0,
                    "total_amount": _sum_money(r.get("total_amount")),
                }
            )

        payload = {
            "date": day.isoformat(),
            "gross": {
                "sales_count": gross.get("sales_count") or 0,
                "total_amount": _sum_money(gross.get("total_amount")),
            },
            "refunds": {
                "refund_count": refund_count,
                "refund_total_amount": _sum_money(refund_total),
            },
            "net": {
                "net_total_amount": _sum_money(gross.get("total_amount"))
                - _sum_money(refund_total),
            },
            "breakdowns": {
                "by_payment_method": [
                    {
                        "payment_method": r.get("payment_method") or "unknown",
                        "count": r.get("count") or 0,
                        "total_amount": _sum_money(r.get("total_amount")),
                    }
                    for r in by_payment_method
                ],
                "by_cashier": by_cashier,
            },
        }
        return Response(payload)


class CashReconciliationReportView(APIView):
    permission_classes = [_AdminOnly]

    def get(self, request):
        day = _parse_date(request.query_params.get("date"))
        sales_qs, start, end = _sales_for_day(day)

        cash_total = 0.0
        non_cash_total = 0.0

        if SalePaymentAllocation is not None:
            alloc_qs = SalePaymentAllocation.objects.filter(
                sale__in=sales_qs,
                created_at__gte=start,
                created_at__lt=end,
            )

            cash_total = _sum_money(
                alloc_qs.filter(method__iexact="cash")
                .aggregate(s=Sum("amount"))
                .get("s")
            )
            non_cash_total = _sum_money(
                alloc_qs.exclude(method__iexact="cash")
                .aggregate(s=Sum("amount"))
                .get("s")
            )
        else:
            cash_total = _sum_money(
                sales_qs.filter(payment_method__iexact="cash")
                .aggregate(s=Sum("total_amount"))
                .get("s")
            )
            non_cash_total = _sum_money(
                sales_qs.exclude(payment_method__iexact="cash")
                .aggregate(s=Sum("total_amount"))
                .get("s")
            )

        by_payment_method = list(
            sales_qs.values("payment_method")
            .annotate(count=Count("id"), total_amount=Sum("total_amount"))
            .order_by("payment_method")
        )

        payload = {
            "date": day.isoformat(),
            "cash_total_amount": cash_total,
            "non_cash_total_amount": non_cash_total,
            "by_payment_method": [
                {
                    "payment_method": r.get("payment_method") or "unknown",
                    "count": r.get("count") or 0,
                    "total_amount": _sum_money(r.get("total_amount")),
                }
                for r in by_payment_method
            ],
        }
        return Response(payload)


class ZReportView(APIView):
    permission_classes = [_AdminOnly]

    def get(self, request):
        day = _parse_date(request.query_params.get("date"))
        sales_qs, start, end = _sales_for_day(day)

        gross = sales_qs.aggregate(
            transaction_count=Count("id"),
            gross_total_amount=Sum("total_amount"),
        )

        refunds_qs = SaleRefundAudit.objects.filter(
            refunded_at__gte=start, refunded_at__lt=end
        )
        refund_total = sum(_refund_amount_from_audit(a) for a in refunds_qs.iterator())

        payload = {
            "date": day.isoformat(),
            "generated_at": timezone.now().isoformat(),
            "z_report": {
                "transaction_count": gross.get("transaction_count") or 0,
                "gross_total_amount": _sum_money(gross.get("gross_total_amount")),
                "refund_total_amount": _sum_money(refund_total),
                "net_total_amount": _sum_money(gross.get("gross_total_amount"))
                - _sum_money(refund_total),
            },
        }
        return Response(payload)
