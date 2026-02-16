# sales/services/refund_service.py

"""
REFUND SERVICE (DOMAIN-CONTROLLED)

Purpose:
- Perform the SALES-domain refund transition with a strict, immutable audit trail.
- This service does NOT restore stock (orchestrator handles stock).
- This service does NOT recalculate money (uses authoritative snapshots).

Golden Rule Compliance:
- File begins with an in-body path comment.
- Docstring included inside code.

HOTSPRINT UPGRADE (COGS + PROFIT READY):
- Creates SaleRefundAudit with full original_* snapshots:
  subtotal/tax/discount/total + cogs + gross profit (from Sale snapshot fields).
- Keeps sale lifecycle rules intact and deterministic.
"""

from django.db import transaction
from django.utils import timezone

from sales.models.sale import Sale
from sales.models.refund_audit import SaleRefundAudit
from sales.services.sale_lifecycle import (
    validate_transition,
    InvalidSaleTransitionError,
)


# ============================================================
# DOMAIN ERRORS
# ============================================================

class RefundError(Exception):
    pass


class InvalidSaleStateError(RefundError):
    pass


class DuplicateRefundError(RefundError):
    pass


class AccountingPostingError(RefundError):
    """
    Raised when refund cannot be posted to the accounting ledger.

    NOTE:
    The refund workflow is a SALES-domain concern, even if ledger posting
    is performed by an accounting service/adapter.
    """
    pass


# ============================================================
# REFUND SERVICE
# ============================================================

@transaction.atomic
def refund_sale(
    *,
    sale: Sale,
    user,
    refund_reason: str | None = None,
) -> Sale:
    """
    FULL SALE REFUND (DOMAIN-CONTROLLED, AUDITED)

    GUARANTEES:
    - No stock mutation (orchestrator handles stock)
    - Does NOT recalculate money (uses snapshots on Sale)
    - Immutable audit trail (SaleRefundAudit)
    - Atomic domain state transition

    FLOW:
    1) Validate lifecycle transition
    2) Ensure not already refunded
    3) Create immutable SaleRefundAudit (snapshot)
    4) Transition sale.status -> REFUNDED
    """

    # --------------------------------------------------
    # 1. LIFECYCLE VALIDATION
    # --------------------------------------------------
    try:
        validate_transition(
            sale=sale,
            target_status=Sale.STATUS_REFUNDED,
        )
    except InvalidSaleTransitionError as exc:
        raise InvalidSaleStateError(str(exc)) from exc

    # --------------------------------------------------
    # 2. DUPLICATE REFUND PROTECTION
    # --------------------------------------------------
    if SaleRefundAudit.objects.filter(sale=sale).exists():
        raise DuplicateRefundError(f"Sale {sale.id} has already been refunded")

    # --------------------------------------------------
    # 3. CREATE IMMUTABLE AUDIT RECORD (SNAPSHOT)
    # --------------------------------------------------
    now = timezone.now()

    SaleRefundAudit.objects.create(
        sale=sale,
        refunded_by=user,
        reason=(refund_reason or "").strip(),
        refunded_at=now,

        # Money snapshots (authoritative)
        original_subtotal_amount=getattr(sale, "subtotal_amount", None) or 0,
        original_tax_amount=getattr(sale, "tax_amount", None) or 0,
        original_discount_amount=getattr(sale, "discount_amount", None) or 0,
        original_total_amount=getattr(sale, "total_amount", None) or 0,

        # Cost/profit snapshots (authoritative)
        original_cogs_amount=getattr(sale, "cogs_amount", None) or 0,
        original_gross_profit_amount=getattr(sale, "gross_profit_amount", None) or 0,
    )

    # --------------------------------------------------
    # 4. STATE TRANSITION ONLY
    # --------------------------------------------------
    sale.status = Sale.STATUS_REFUNDED

    # DO NOT overwrite completed_at (it defines when the sale occurred).
    # If Sale has a refunded_at field, set it; otherwise rely on the audit record.
    update_fields = ["status"]

    if hasattr(sale, "refunded_at"):
        sale.refunded_at = now
        update_fields.append("refunded_at")

    sale.save(update_fields=update_fields)

    return sale
