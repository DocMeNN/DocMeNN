"""
======================================================
PATH: sales/services/refund_orchestrator.py
======================================================
REFUND ORCHESTRATOR (APPLICATION SERVICE)

Purpose:
- Coordinate FULL and PARTIAL refund workflows atomically.
- Enforce strict per-item quantity ceilings for partial refunds.
- Restore stock deterministically (via FIFO/FEFO stock engine).
- Post correct accounting reversals.
- Preserve immutable audit guarantees.

Refund Modes:
1) FULL REFUND
   - items is None or []
   - Creates immutable SaleRefundAudit (one-time)
   - Transitions sale.status -> REFUNDED
   - Restores ALL remaining refundable stock movements
   - Posts FULL refund reversal to ledger

2) PARTIAL REFUND
   - items provided [{sale_item_id, quantity}, ...]
   - Creates immutable SaleItemRefund rows (append-only, multi)
   - Restores stock ONLY for requested quantities (uses stock engine ceilings)
   - Posts PARTIAL refund reversal to ledger
   - Sale may remain COMPLETED (or optionally PARTIALLY_REFUNDED if the model supports it)
   - When cumulative partials reach full quantity, we finalize by creating SaleRefundAudit
     and transitioning status -> REFUNDED WITHOUT re-posting ledger or re-restoring stock.

Notes:
- No frontend assumptions are made here.
- UI can be added later without changing this logic.

Golden Rule Compliance:
- Full file replacement (copy & replace).
"""

from __future__ import annotations

from collections import defaultdict

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Sum

from accounting.services.exceptions import (
    AccountResolutionError,
    IdempotencyError,
    JournalEntryCreationError,
)
from permissions.roles import ROLE_ADMIN, ROLE_PHARMACIST
from products.services.stock_fifo import restore_stock_from_sale
from sales.models.refund_audit import SaleRefundAudit
from sales.models.sale import Sale
from sales.models.sale_item import SaleItem
from sales.models.sale_item_refund import SaleItemRefund
from sales.services.refund_service import refund_sale

ALLOWED_REFUND_ROLES = {ROLE_ADMIN, ROLE_PHARMACIST}


class RefundOrchestratorError(Exception):
    pass


def _assert_user_can_refund(*, user):
    if not user or not getattr(user, "is_authenticated", False):
        raise PermissionDenied("Authentication required to refund a sale.")

    user_role = getattr(user, "role", None)
    if user_role not in ALLOWED_REFUND_ROLES:
        raise PermissionDenied(
            f"Users with role '{user_role}' are not allowed to refund sales."
        )


def _to_int_qty(value) -> int:
    try:
        v = int(value)
    except Exception:
        return 0
    return v


def _normalize_partial_items(*, sale: Sale, items: list[dict]) -> list[dict]:
    """
    Normalize partial refund items:
    - Must be list of dicts with {sale_item_id, quantity}
    - quantity must be int >= 1
    - Aggregates duplicates by sale_item_id
    - Validates sale_item_id belongs to sale
    """
    if not isinstance(items, list) or not items:
        raise ValidationError("Partial refund requires items.")

    if not hasattr(sale, "items"):
        raise ValidationError(
            "Sale items relation not available; cannot process partial refund."
        )

    sale_items = list(sale.items.all())
    sale_item_ids = {str(si.id) for si in sale_items}
    if not sale_item_ids:
        raise ValidationError("Sale has no items; cannot refund.")

    agg: dict[str, int] = defaultdict(int)

    for line in items:
        if not isinstance(line, dict):
            raise ValidationError("Refund items must be objects.")

        sid = str(line.get("sale_item_id") or "").strip()
        if not sid:
            raise ValidationError("Each refund item must include sale_item_id.")

        if sid not in sale_item_ids:
            raise ValidationError(f"Invalid sale_item_id: {sid}")

        qty = _to_int_qty(line.get("quantity") or 0)
        if qty <= 0:
            raise ValidationError("Refund quantity must be an integer >= 1.")

        agg[sid] += qty

    normalized = [
        {"sale_item_id": sid, "quantity": qty} for sid, qty in agg.items() if qty > 0
    ]
    if not normalized:
        raise ValidationError("No valid refund lines provided.")

    return normalized


def _already_refunded_qty_for_sale_item(*, sale_item: SaleItem) -> int:
    return int(
        SaleItemRefund.objects.filter(sale_item=sale_item)
        .aggregate(total=Sum("quantity_refunded"))
        .get("total")
        or 0
    )


def _ensure_partial_ceiling(*, sale: Sale, normalized_items: list[dict]):
    """
    Enforce per-item ceilings using SaleItemRefund history:
    - cannot refund more than (sold - already_refunded) for each sale item
    """
    sale_items_by_id = {str(si.id): si for si in sale.items.all()}

    for line in normalized_items:
        sid = str(line["sale_item_id"])
        qty = int(line["quantity"])

        si = sale_items_by_id.get(sid)
        if si is None:
            raise ValidationError(f"Invalid sale_item_id: {sid}")

        sold_qty = int(getattr(si, "quantity", 0) or 0)
        already = _already_refunded_qty_for_sale_item(sale_item=si)
        remaining = sold_qty - already

        if remaining <= 0:
            raise ValidationError(f"Item {sid} has no refundable quantity remaining.")

        if qty > remaining:
            raise ValidationError(
                f"Over-refund detected for item {sid}. "
                f"Remaining refundable qty: {remaining}, requested: {qty}"
            )


def _create_item_refund_rows(
    *, sale: Sale, user, reason: str | None, normalized_items: list[dict]
) -> list[SaleItemRefund]:
    """
    Create immutable SaleItemRefund rows (append-only).
    Snapshots price/cost from SaleItem (authoritative snapshot fields).
    """
    sale_items_by_id = {str(si.id): si for si in sale.items.all()}
    rows: list[SaleItemRefund] = []

    for line in normalized_items:
        sid = str(line["sale_item_id"])
        qty = int(line["quantity"])
        si = sale_items_by_id[sid]

        rows.append(
            SaleItemRefund(
                sale=sale,
                sale_item=si,
                quantity_refunded=qty,
                unit_price_snapshot=getattr(si, "unit_price", 0) or 0,
                unit_cost_snapshot=getattr(si, "unit_cost", 0) or 0,
                refunded_by=user,
                reason=(reason or "").strip() or None,
            )
        )

    created = SaleItemRefund.objects.bulk_create(rows)
    return list(created)


def _post_partial_refund_to_ledger(*, sale: Sale, refund_rows: list[SaleItemRefund]):
    """
    Posts a partial refund reversal to the ledger.

    Requires a function in accounting/services/posting.py:
      post_partial_refund_to_ledger(sale=..., refund_items=[SaleItemRefund,...])

    We intentionally hard-fail if it is missing, because silent fallbacks
    would corrupt accounting.
    """
    try:
        from accounting.services.posting import post_partial_refund_to_ledger
    except Exception as exc:
        raise RefundOrchestratorError(
            "Partial refund posting is not available yet. "
            "Expected accounting.services.posting.post_partial_refund_to_ledger()."
        ) from exc

    return post_partial_refund_to_ledger(sale=sale, refund_items=refund_rows)


def _maybe_mark_sale_partially_refunded(*, sale: Sale):
    """
    If Sale supports STATUS_PARTIALLY_REFUNDED, set it.
    Otherwise, leave as COMPLETED (safe with immutable money fields).
    """
    status_partial = getattr(Sale, "STATUS_PARTIALLY_REFUNDED", None)
    if status_partial:
        sale.status = status_partial
        sale.save(update_fields=["status"])


def _maybe_finalize_to_full_refund(*, sale: Sale, user):
    """
    If cumulative item refunds reach full sold quantities:
    - create SaleRefundAudit + transition status -> REFUNDED using refund_sale()
    - DO NOT restore stock (already restored via partials)
    - DO NOT post full ledger reversal (already reversed via partials)
    """
    total_sold = 0
    for si in sale.items.all():
        total_sold += int(getattr(si, "quantity", 0) or 0)

    total_refunded = int(
        SaleItemRefund.objects.filter(sale=sale)
        .aggregate(total=Sum("quantity_refunded"))
        .get("total")
        or 0
    )

    if total_sold > 0 and total_refunded >= total_sold:
        # This creates the immutable audit + status transition only.
        refund_sale(
            sale=sale,
            user=user,
            refund_reason="Auto-finalized after cumulative partial refunds",
        )
        return True

    return False


@transaction.atomic
def refund_sale_with_stock_restoration(
    *,
    sale: Sale,
    user,
    refund_reason: str | None = None,
    items: list[dict] | None = None,
) -> Sale:
    """
    Refund orchestrator (FULL or PARTIAL), atomic.

    FULL refund:
      - items is None or []
      - domain refund -> audit + status
      - restore all stock
      - post full ledger reversal

    PARTIAL refund:
      - items provided
      - enforce ceilings
      - create SaleItemRefund rows
      - restore stock for requested quantities
      - post partial ledger reversal
      - optionally mark status partially_refunded
      - if cumulative hits full: finalize with audit+status only
    """
    _assert_user_can_refund(user=user)

    # --------------------------------------------------
    # FULL REFUND
    # --------------------------------------------------
    if not items:
        # Domain transition (audit + status)
        refunded_sale = refund_sale(
            sale=sale,
            user=user,
            refund_reason=refund_reason,
        )

        # Must exist now
        refund_audit = SaleRefundAudit.objects.select_related("sale").get(
            sale=refunded_sale
        )

        # Stock restoration (full)
        restore_stock_from_sale(
            sale=refunded_sale,
            user=user,
            items=None,
        )

        # Ledger posting (full reversal)
        try:
            from accounting.services.posting import post_refund_to_ledger

            post_refund_to_ledger(sale=refunded_sale, refund_audit=refund_audit)
        except (
            JournalEntryCreationError,
            IdempotencyError,
            AccountResolutionError,
        ) as exc:
            raise RefundOrchestratorError(str(exc)) from exc
        except Exception as exc:
            raise RefundOrchestratorError(
                f"Refund ledger posting failed: {exc}"
            ) from exc

        return refunded_sale

    # --------------------------------------------------
    # PARTIAL REFUND
    # --------------------------------------------------
    # Only refundable when sale is completed (or partially refunded if supported)
    allowed_statuses = {Sale.STATUS_COMPLETED}
    maybe_partial = getattr(Sale, "STATUS_PARTIALLY_REFUNDED", None)
    if maybe_partial:
        allowed_statuses.add(maybe_partial)

    if getattr(sale, "status", None) not in allowed_statuses:
        raise ValidationError("Sale is not refundable in its current state.")

    normalized_items = _normalize_partial_items(sale=sale, items=items)
    _ensure_partial_ceiling(sale=sale, normalized_items=normalized_items)

    # Create immutable refund rows (append-only)
    refund_rows = _create_item_refund_rows(
        sale=sale,
        user=user,
        reason=refund_reason,
        normalized_items=normalized_items,
    )

    # Restore stock for requested quantities (service enforces ceilings via movements)
    restore_stock_from_sale(
        sale=sale,
        user=user,
        items=normalized_items,
    )

    # Post proportional reversal
    try:
        _post_partial_refund_to_ledger(sale=sale, refund_rows=refund_rows)
    except (JournalEntryCreationError, IdempotencyError, AccountResolutionError) as exc:
        raise RefundOrchestratorError(str(exc)) from exc
    except RefundOrchestratorError:
        raise
    except Exception as exc:
        raise RefundOrchestratorError(
            f"Partial refund ledger posting failed: {exc}"
        ) from exc

    # Update status if supported
    _maybe_mark_sale_partially_refunded(sale=sale)

    # If this partial makes it fully refunded, finalize state + audit only
    _maybe_finalize_to_full_refund(sale=sale, user=user)

    return sale
