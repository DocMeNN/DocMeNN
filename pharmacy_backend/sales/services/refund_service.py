# sales/services/refund_service.py

from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from products.services.stock_fifo import restore_stock_from_sale
from sales.models.refund_audit import SaleRefundAudit
from sales.models.sale import Sale


class RefundError(Exception):
    pass


class OverRefundError(RefundError):
    pass


@transaction.atomic
def refund_sale(
    *,
    sale: Sale,
    user,
    subtotal_amount: Decimal,
    tax_amount: Decimal,
    discount_amount: Decimal,
    cogs_amount: Decimal,
    reason: str | None = None,
    items: list | None = None,
):
    """
    CENTRAL REFUND DOMAIN SERVICE

    Responsibilities
    ----------------
    1. Restore inventory via FIFO engine
    2. Record financial refund audit
    3. Prevent over-refund
    4. Maintain accounting correctness
    """

    if sale.status not in (Sale.STATUS_COMPLETED, Sale.STATUS_REFUNDED):
        raise RefundError("Sale is not refundable")

    subtotal_amount = Decimal(subtotal_amount or 0)
    tax_amount = Decimal(tax_amount or 0)
    discount_amount = Decimal(discount_amount or 0)
    cogs_amount = Decimal(cogs_amount or 0)

    total_amount = subtotal_amount + tax_amount - discount_amount
    gross_profit_amount = subtotal_amount - cogs_amount

    # --------------------------------------------------
    # LOCK SALE FOR CONCURRENCY SAFETY
    # --------------------------------------------------
    sale = Sale.objects.select_for_update().get(pk=sale.pk)

    # --------------------------------------------------
    # CALCULATE ALREADY REFUNDED
    # --------------------------------------------------
    already_refunded = (
        sale.refund_audits.aggregate(total=Sum("total_amount"))["total"]
        or Decimal("0.00")
    )

    remaining = Decimal(sale.total_amount) - Decimal(already_refunded)

    if total_amount > remaining:
        raise OverRefundError(
            f"Refund exceeds remaining balance. Remaining={remaining}"
        )

    # --------------------------------------------------
    # 🔑 INVENTORY RESTORATION (CRITICAL FIX)
    # --------------------------------------------------
    restore_stock_from_sale(
        sale=sale,
        user=user,
        items=items,
    )

    # --------------------------------------------------
    # FINANCIAL AUDIT RECORD
    # --------------------------------------------------
    refund = SaleRefundAudit.objects.create(
        sale=sale,
        refunded_by=user,
        reason=(reason or "").strip(),
        refunded_at=timezone.now(),
        subtotal_amount=subtotal_amount,
        tax_amount=tax_amount,
        discount_amount=discount_amount,
        total_amount=total_amount,
        cogs_amount=cogs_amount,
        gross_profit_amount=gross_profit_amount,
    )

    # --------------------------------------------------
    # UPDATE SALE STATUS
    # --------------------------------------------------
    if (already_refunded + total_amount) >= sale.total_amount:
        sale.status = Sale.STATUS_REFUNDED
        sale.save(update_fields=["status"])

    return refund