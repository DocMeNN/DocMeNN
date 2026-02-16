# products/services/stock_fifo.py

"""
FIFO STOCK ENGINE (PHASE 2)

Purpose:
- Deduct stock using FEFO/FIFO (earliest expiry first, then oldest batch).
- Restore stock safely from sale movements (refund-safe).
- Integer-only quantities (StockMovement.quantity is PositiveIntegerField).

TRANSITION NOTE:
- During migration, StockBatch.store may be NULL for legacy rows.
- We allow a SAFE fallback to NULL-store batches ONLY when the requested store has
  no batches for that product. This prevents hard "Available: 0" while you backfill.

HOTSPRINT UPGRADE (PURCHASE-COST + PROFIT READY):
- Every StockMovement created by this service MUST carry unit_cost_snapshot.
- SALE movements snapshot batch.unit_cost (FIFO cost basis).
- REFUND movements snapshot the ORIGINAL sale movement unit_cost_snapshot
  (audit-safe reversal; prevents cost drift).

HOTSPRINT UPGRADE (PARTIAL REFUNDS READY):
- restore_stock_from_sale() now supports partial restoration via `items`.
- Idempotency is enforced by quantity ceilings (cannot restore more than sold),
  not by a hard “already refunded” block.
"""

from __future__ import annotations

from decimal import Decimal
from collections import defaultdict

from django.db import transaction
from django.utils import timezone

from products.models import StockBatch, StockMovement


# ============================================================
# DOMAIN ERRORS
# ============================================================

class InsufficientStockError(Exception):
    pass


class StockRestorationError(Exception):
    pass


def _to_int_qty(value) -> int:
    """
    Quantity normalizer.
    HARD RULE: quantities are integer units in this system.
    """
    if value is None or value == "":
        return 0

    if isinstance(value, bool):
        raise ValueError("quantity must be a whole integer unit")

    if isinstance(value, int):
        return value

    if isinstance(value, str):
        s = value.strip()
        if s.isdigit():
            return int(s)

    raise ValueError("quantity must be a whole integer unit")


def _resolve_store_id(*, product, store=None):
    """
    Store scope resolver.
    Priority:
    1) explicit store argument
    2) product.store
    """
    if store is not None:
        return getattr(store, "id", store)
    return getattr(product, "store_id", None)


def _get_batches_qs(*, product, store_id, today):
    """
    Canonical batch query for deduction.

    Primary:
      store_id = selected store

    Transitional fallback:
      if no batches exist for this store+product, but NULL-store batches exist,
      use NULL-store batches so checkout doesn't falsely show Available: 0.
    """
    base = StockBatch.objects.filter(
        product=product,
        is_active=True,
        expiry_date__gte=today,
        quantity_remaining__gt=0,
    )

    store_qs = base.filter(store_id=store_id)
    if store_qs.exists():
        return store_qs

    null_store_qs = base.filter(store__isnull=True)
    if null_store_qs.exists():
        return null_store_qs

    return store_qs


def _require_batch_cost(batch: StockBatch) -> Decimal:
    """
    Accounting-grade rule:
    We cannot do FIFO COGS without a cost basis.

    NOTE:
    StockBatch.unit_cost is allowed to be NULL for legacy batches during migration,
    but SALE/REFUND cost posting must not proceed from unknown-cost batches.
    """
    raw = getattr(batch, "unit_cost", None)
    if raw is None:
        raise ValueError(
            "StockBatch.unit_cost is missing for an available batch. "
            "This system requires purchase-based stock intake with unit_cost. "
            "Backfill legacy batches or restrict them from sale."
        )
    try:
        unit_cost = Decimal(str(raw))
    except Exception as exc:
        raise ValueError("StockBatch.unit_cost must be a valid decimal") from exc

    if unit_cost <= Decimal("0.00"):
        raise ValueError("StockBatch.unit_cost must be > 0")

    return unit_cost


# ============================================================
# FIFO DEDUCTION
# ============================================================

@transaction.atomic
def deduct_stock_fifo(*, product, quantity, user=None, sale=None, store=None):
    """
    Deduct stock using FIFO/FEFO (First-Expiry-First-Out), STORE-SCOPED.

    HARD RULE:
    - If we record StockMovement.Reason.SALE, a sale reference is REQUIRED.

    HOTSPRINT RULE:
    - Every SALE movement must store unit_cost_snapshot from the batch.
    """
    if not product:
        raise ValueError("product is required")

    if sale is None:
        raise ValueError(
            "sale is required for FIFO deduction (StockMovement requires a sale reference)."
        )

    store_id = _resolve_store_id(product=product, store=store)
    if not store_id:
        raise ValueError("store is required (either pass store or ensure product.store is set)")

    qty = _to_int_qty(quantity)
    if qty <= 0:
        return []

    today = timezone.localdate()
    remaining_qty = qty
    movements = []

    batches_qs = (
        _get_batches_qs(product=product, store_id=store_id, today=today)
        .select_for_update()
        .order_by("expiry_date", "created_at")
    )

    batch_list = list(batches_qs)
    total_available = sum(int(b.quantity_remaining or 0) for b in batch_list)

    if total_available < remaining_qty:
        raise InsufficientStockError(
            f"Insufficient stock for {getattr(product, 'name', 'product')}. "
            f"Requested: {qty}, Available: {total_available}"
        )

    for batch in batch_list:
        if remaining_qty <= 0:
            break

        available = int(batch.quantity_remaining or 0)
        if available <= 0:
            continue

        consumed = available if available <= remaining_qty else remaining_qty

        # Enforce cost basis existence before we commit movements
        unit_cost = _require_batch_cost(batch)

        # Update remaining qty
        batch.quantity_remaining = available - consumed
        batch.is_active = batch.quantity_remaining > 0
        batch.save(update_fields=["quantity_remaining", "is_active"])

        # Create SALE movement with cost snapshot
        movements.append(
            StockMovement.objects.create(
                product=product,
                batch=batch,
                movement_type=StockMovement.MovementType.OUT,
                reason=StockMovement.Reason.SALE,
                quantity=consumed,
                unit_cost_snapshot=unit_cost,
                performed_by=user,
                sale=sale,
            )
        )

        remaining_qty -= consumed

    return movements


# ============================================================
# STOCK RESTORATION (REFUND-SAFE, PARTIAL-READY)
# ============================================================

def _normalize_refund_items(*, sale, items):
    """
    Normalize refund items into a product->qty map.

    Accepts (best-effort):
    - [{"sale_item_id": "...", "quantity": 2}, ...]
    - [{"product_id": "...", "quantity": 2}, ...]
    - [{"product": "...", "quantity": 2}, ...] (legacy-ish)

    Validation (strict enough to prevent nonsense):
    - quantity must be integer >= 1
    - if sale_item_id provided: must belong to sale and qty <= sold qty for that item
    - aggregates quantities by product_id
    """
    if not items:
        return None  # means "restore everything remaining"

    # Import locally to avoid app-level circular imports at module load time.
    try:
        from sales.models import SaleItem
    except Exception:
        SaleItem = None

    requested_by_product = defaultdict(int)

    for line in items:
        if not isinstance(line, dict):
            raise StockRestorationError("Refund items must be objects")

        qty = _to_int_qty(line.get("quantity"))
        if qty <= 0:
            raise StockRestorationError("Refund quantity must be >= 1")

        sale_item_id = line.get("sale_item_id")
        if sale_item_id and SaleItem is not None:
            si = (
                SaleItem.objects
                .select_related("product", "sale")
                .filter(id=sale_item_id, sale=sale)
                .first()
            )
            if si is None:
                raise StockRestorationError(f"Invalid sale_item_id: {sale_item_id}")

            sold_qty = int(getattr(si, "quantity", 0) or 0)
            if qty > sold_qty:
                raise StockRestorationError(
                    f"Refund qty exceeds sold qty for item {sale_item_id}. "
                    f"Sold: {sold_qty}, Requested: {qty}"
                )

            pid = getattr(si, "product_id", None)
            if not pid:
                raise StockRestorationError("SaleItem has no product reference")
            requested_by_product[str(pid)] += qty
            continue

        # Product direct
        pid = line.get("product_id") or line.get("product")
        if not pid:
            raise StockRestorationError(
                "Refund item must include sale_item_id or product_id"
            )
        requested_by_product[str(pid)] += qty

    if not requested_by_product:
        return None

    return dict(requested_by_product)


@transaction.atomic
def restore_stock_from_sale(*, sale, user=None, items=None):
    """
    Restore stock by reversing SALE movements.

    Supports:
    - FULL restoration (default, items=None)
    - PARTIAL restoration (items provided)
    - MULTIPLE partial restorations over time
      (idempotency is enforced by not exceeding originally sold quantities).

    HARD RULES:
    - Must have SALE movements
    - Cannot restore more than sold for each batch movement

    HOTSPRINT RULE:
    - REFUND movement snapshots the ORIGINAL SALE unit_cost_snapshot
      (audit-safe reversal; prevents cost drift).
    """
    if sale is None:
        raise ValueError("sale is required")

    requested_by_product = _normalize_refund_items(sale=sale, items=items)

    sale_movements_qs = (
        StockMovement.objects
        .select_for_update()
        .filter(
            sale=sale,
            reason=StockMovement.Reason.SALE,
            movement_type=StockMovement.MovementType.OUT,
        )
        .select_related("batch", "product")
        .order_by("created_at", "id")
    )

    sale_movement_list = list(sale_movements_qs)
    if not sale_movement_list:
        raise StockRestorationError(f"No SALE stock movements found for sale {sale.id}")

    # Sum already-refunded quantities per (batch_id, product_id)
    refund_movements = (
        StockMovement.objects
        .filter(
            sale=sale,
            reason=StockMovement.Reason.REFUND,
            movement_type=StockMovement.MovementType.IN,
        )
        .values("batch_id", "product_id")
    )

    already_refunded = defaultdict(int)
    for row in refund_movements.annotate():
        # NOTE: .values() result has keys, no quantities yet; we aggregate below with a second query
        pass

    # Proper aggregation
    from django.db.models import Sum
    refund_agg = (
        StockMovement.objects
        .filter(
            sale=sale,
            reason=StockMovement.Reason.REFUND,
            movement_type=StockMovement.MovementType.IN,
        )
        .values("batch_id", "product_id")
        .annotate(total_qty=Sum("quantity"))
    )
    for r in refund_agg:
        already_refunded[(r["batch_id"], r["product_id"])] = int(r["total_qty"] or 0)

    # Helper: how much we still need to restore for this product
    remaining_by_product = None
    if requested_by_product is not None:
        remaining_by_product = {k: int(v or 0) for k, v in requested_by_product.items()}

    created = []

    for sale_mv in sale_movement_list:
        batch_id = sale_mv.batch_id
        product_id = sale_mv.product_id

        sold_qty = int(getattr(sale_mv, "quantity", 0) or 0)
        if sold_qty <= 0:
            continue

        already_qty = int(already_refunded.get((batch_id, product_id), 0) or 0)
        remaining_sold_qty = sold_qty - already_qty

        if remaining_sold_qty <= 0:
            continue  # this movement already fully refunded

        # If partial requested: skip products not requested
        if remaining_by_product is not None:
            need = int(remaining_by_product.get(str(product_id), 0) or 0)
            if need <= 0:
                continue
            restore_qty = remaining_sold_qty if remaining_sold_qty <= need else need
        else:
            # Full restore of everything remaining
            restore_qty = remaining_sold_qty

        if restore_qty <= 0:
            continue

        # Lock and update batch
        batch = StockBatch.objects.select_for_update().get(pk=batch_id)

        batch.quantity_remaining = int(batch.quantity_remaining or 0) + int(restore_qty)
        batch.is_active = batch.quantity_remaining > 0
        batch.save(update_fields=["quantity_remaining", "is_active"])

        original_unit_cost = getattr(sale_mv, "unit_cost_snapshot", None)
        if original_unit_cost is None:
            # Legacy fallback (should be rare after hotsprint)
            original_unit_cost = _require_batch_cost(batch)

        created.append(
            StockMovement.objects.create(
                product=sale_mv.product,
                batch=batch,
                movement_type=StockMovement.MovementType.IN,
                reason=StockMovement.Reason.REFUND,
                quantity=int(restore_qty),
                unit_cost_snapshot=original_unit_cost,
                performed_by=user,
                sale=sale,
            )
        )

        # Update trackers
        already_refunded[(batch_id, product_id)] = already_qty + int(restore_qty)

        if remaining_by_product is not None:
            remaining_by_product[str(product_id)] = need - int(restore_qty)

    # If partial was requested, ensure we satisfied it fully
    if remaining_by_product is not None:
        missing = {pid: qty for pid, qty in remaining_by_product.items() if int(qty) > 0}
        if missing:
            raise StockRestorationError(
                f"Unable to restore requested refund quantities (insufficient refundable stock history). "
                f"Missing by product: {missing}"
            )

    if not created:
        # This means either:
        # - everything was already refunded, OR
        # - requested items didn't match any sale movements
        raise StockRestorationError(
            f"No refundable stock movements remaining for sale {sale.id}."
        )

    return created
