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

Refund reporting (CRITICAL):
- Partial refunds are recorded as SaleItemRefund rows (append-only).
- Full refunds are recorded as SaleRefundAudit (one-time).
- Reports MUST include BOTH, without double-counting.

Rule:
- Refund EVENTS for the day:
  - Partial refunds: SaleItemRefund.refunded_at in [start, end)
  - Full refunds: SaleRefundAudit.refunded_at in [start, end)
    BUT exclude audits for sales that have SaleItemRefund history
    (prevents double-counting and avoids auto-finalize attribution errors)

Cash reconciliation (REFUND-AWARE):
- Cash In: allocations for sales of the day
- Cash Out: refund events of the day, pro-rated across the original sale allocations
- Net: In - Out

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

try:
    from sales.models.sale_item_refund import SaleItemRefund
except Exception:
    SaleItemRefund = None


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


def _refund_amount_from_item_refund(row) -> float:
    """
    SaleItemRefund provides an authoritative computed line total:
      line_total_refund_amount = unit_price_snapshot * quantity_refunded
    """
    if hasattr(row, "line_total_refund_amount"):
        return _sum_money(row.line_total_refund_amount)

    qty = getattr(row, "quantity_refunded", 0) or 0
    unit_price = getattr(row, "unit_price_snapshot", 0) or 0
    try:
        return float(unit_price) * float(int(qty))
    except Exception:
        return 0.0


def _sales_for_day(day: date_cls):
    start, end = _date_bounds(day)

    # Prefer completed_at for "real sales date"
    qs = Sale.objects.filter(completed_at__gte=start, completed_at__lt=end)
    if not qs.exists():
        qs = Sale.objects.filter(created_at__gte=start, created_at__lt=end)

    return qs, start, end


def _refunds_for_day(*, start, end):
    """
    Returns (refund_count, refund_total_amount) for the day.

    Includes:
    - Partial refunds from SaleItemRefund (refunded_at in day)
    - Full refunds from SaleRefundAudit (refunded_at in day),
      excluding audits for sales that have SaleItemRefund history.
    """
    refund_count = 0
    refund_total = 0.0

    sales_with_item_refunds = set()

    # 1) PARTIAL REFUNDS
    if SaleItemRefund is not None:
        item_qs = SaleItemRefund.objects.filter(
            refunded_at__gte=start, refunded_at__lt=end
        )
        refund_count += item_qs.count()
        refund_total += sum(_refund_amount_from_item_refund(r) for r in item_qs.iterator())

        # used to exclude audits for auto-finalization / double counting
        sales_with_item_refunds = set(
            SaleItemRefund.objects.values_list("sale_id", flat=True).distinct()
        )

    # 2) FULL REFUNDS
    audit_qs = SaleRefundAudit.objects.filter(refunded_at__gte=start, refunded_at__lt=end)
    if sales_with_item_refunds:
        audit_qs = audit_qs.exclude(sale_id__in=list(sales_with_item_refunds))

    refund_count += audit_qs.count()
    refund_total += sum(_refund_amount_from_audit(a) for a in audit_qs.iterator())

    return refund_count, refund_total


def _refund_events_for_day_by_sale(*, start, end) -> dict[str, float]:
    """
    Build {sale_id(str): refund_amount_for_day(float)} for refund EVENTS occurring in the day.

    - Partial refunds: sum SaleItemRefund.line_total_refund_amount grouped by sale_id for day.
    - Full refunds: sum SaleRefundAudit refund amount grouped by sale_id for day,
      excluding audits for sales that have any SaleItemRefund history (avoid double count).
    """
    by_sale: dict[str, float] = {}

    sales_with_item_refunds = set()

    if SaleItemRefund is not None:
        partial_qs = SaleItemRefund.objects.filter(
            refunded_at__gte=start, refunded_at__lt=end
        )

        for r in partial_qs.iterator():
            sid = str(getattr(r, "sale_id", "") or "")
            if not sid:
                continue
            by_sale[sid] = by_sale.get(sid, 0.0) + _refund_amount_from_item_refund(r)

        sales_with_item_refunds = set(
            SaleItemRefund.objects.values_list("sale_id", flat=True).distinct()
        )

    audit_qs = SaleRefundAudit.objects.filter(refunded_at__gte=start, refunded_at__lt=end)
    if sales_with_item_refunds:
        audit_qs = audit_qs.exclude(sale_id__in=list(sales_with_item_refunds))

    for a in audit_qs.iterator():
        sid = str(getattr(a, "sale_id", "") or "")
        if not sid:
            continue
        by_sale[sid] = by_sale.get(sid, 0.0) + _refund_amount_from_audit(a)

    return by_sale


def _allocate_refund_out_by_method(*, refund_by_sale: dict[str, float]) -> dict[str, float]:
    """
    Attribute refund-out amounts to payment methods by pro-rating across the sale's
    original payment allocations.

    Returns:
      {
        "cash": 12.34,
        "non_cash": 56.78,
        "unknown": 0.00
      }
    """
    out = {"cash": 0.0, "non_cash": 0.0, "unknown": 0.0}

    if not refund_by_sale:
        return out

    if SalePaymentAllocation is None:
        # no allocation table available -> cannot attribute by method
        out["unknown"] = float(sum(refund_by_sale.values()))
        return out

    sale_ids = list(refund_by_sale.keys())

    allocs = (
        SalePaymentAllocation.objects.filter(sale_id__in=sale_ids)
        .values("sale_id", "method")
        .annotate(total=Sum("amount"))
    )

    alloc_by_sale: dict[str, list[dict]] = {}
    for row in allocs:
        sid = str(row["sale_id"])
        alloc_by_sale.setdefault(sid, []).append(
            {"method": (row.get("method") or "").lower(), "total": _sum_money(row.get("total"))}
        )

    for sid, refund_amt in refund_by_sale.items():
        refund_amt = float(refund_amt or 0.0)
        if refund_amt <= 0:
            continue

        legs = alloc_by_sale.get(sid) or []
        legs_total = sum(l["total"] for l in legs)

        if legs_total <= 0:
            out["unknown"] += refund_amt
            continue

        # pro-rate
        for leg in legs:
            share = (leg["total"] / legs_total) if legs_total else 0.0
            portion = refund_amt * share
            if (leg["method"] or "").lower() == "cash":
                out["cash"] += portion
            else:
                out["non_cash"] += portion

    return out


class DailySalesReportView(APIView):
    permission_classes = [_AdminOnly]

    def get(self, request):
        day = _parse_date(request.query_params.get("date"))
        sales_qs, start, end = _sales_for_day(day)

        gross = sales_qs.aggregate(
            sales_count=Count("id"),
            total_amount=Sum("total_amount"),
        )

        refund_count, refund_total = _refunds_for_day(start=start, end=end)

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

        # -----------------------------
        # SALES IN (for the day's sales)
        # -----------------------------
        cash_in = 0.0
        non_cash_in = 0.0

        if SalePaymentAllocation is not None:
            alloc_qs = SalePaymentAllocation.objects.filter(sale__in=sales_qs)

            cash_in = _sum_money(
                alloc_qs.filter(method__iexact="cash")
                .aggregate(s=Sum("amount"))
                .get("s")
            )
            non_cash_in = _sum_money(
                alloc_qs.exclude(method__iexact="cash")
                .aggregate(s=Sum("amount"))
                .get("s")
            )
        else:
            cash_in = _sum_money(
                sales_qs.filter(payment_method__iexact="cash")
                .aggregate(s=Sum("total_amount"))
                .get("s")
            )
            non_cash_in = _sum_money(
                sales_qs.exclude(payment_method__iexact="cash")
                .aggregate(s=Sum("total_amount"))
                .get("s")
            )

        # -----------------------------
        # REFUNDS OUT (events that day)
        # -----------------------------
        refund_by_sale = _refund_events_for_day_by_sale(start=start, end=end)
        out_by_method = _allocate_refund_out_by_method(refund_by_sale=refund_by_sale)

        cash_out = float(out_by_method.get("cash") or 0.0)
        non_cash_out = float(out_by_method.get("non_cash") or 0.0)
        unknown_out = float(out_by_method.get("unknown") or 0.0)

        # NET
        cash_net = cash_in - cash_out
        non_cash_net = non_cash_in - non_cash_out

        by_payment_method = list(
            sales_qs.values("payment_method")
            .annotate(count=Count("id"), total_amount=Sum("total_amount"))
            .order_by("payment_method")
        )

        payload = {
            "date": day.isoformat(),

            # Backward-compatible keys (now NET, refund-aware)
            "cash_total_amount": cash_net,
            "non_cash_total_amount": non_cash_net,

            # New transparency fields (won’t break consumers that ignore them)
            "sales_in": {
                "cash_in_amount": cash_in,
                "non_cash_in_amount": non_cash_in,
            },
            "refunds_out": {
                "cash_out_amount": cash_out,
                "non_cash_out_amount": non_cash_out,
                "unknown_out_amount": unknown_out,
            },
            "net": {
                "cash_net_amount": cash_net,
                "non_cash_net_amount": non_cash_net,
                "total_net_amount": (cash_net + non_cash_net),
            },

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

        refund_count, refund_total = _refunds_for_day(start=start, end=end)

        payload = {
            "date": day.isoformat(),
            "generated_at": timezone.now().isoformat(),
            "z_report": {
                "transaction_count": gross.get("transaction_count") or 0,
                "gross_total_amount": _sum_money(gross.get("gross_total_amount")),
                "refund_count": refund_count,
                "refund_total_amount": _sum_money(refund_total),
                "net_total_amount": _sum_money(gross.get("gross_total_amount"))
                - _sum_money(refund_total),
            },
        }
        return Response(payload)