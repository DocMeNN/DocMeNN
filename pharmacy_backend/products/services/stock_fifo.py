# FULL FILE (event enabled FIFO engine)

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from products.models import StockBatch, StockMovement

from backend.events.event_bus import publish
from backend.events.domain.inventory_events import (
    StockDeducted,
    StockRestored,
)


class InsufficientStockError(Exception):
    pass


class StockRestorationError(Exception):
    pass


def _to_int_qty(value) -> int:

    if value is None or value == "":
        return 0

    if isinstance(value, bool):
        raise ValueError("quantity must be integer")

    if isinstance(value, int):
        return value

    if isinstance(value, str):
        s = value.strip()
        if s.isdigit():
            return int(s)

    raise ValueError("quantity must be integer")


def _resolve_store_id(*, product, store=None):

    if store is not None:
        return getattr(store, "id", store)

    return getattr(product, "store_id", None)


def _get_batches_qs(*, product, store_id, today):

    base = StockBatch.objects.filter(
        product=product,
        expiry_date__gte=today,
        quantity_remaining__gt=0,
    )

    if store_id is None:
        return base.filter(store__isnull=True)

    store_qs = base.filter(store_id=store_id)

    if store_qs.exists():
        return store_qs

    null_store_qs = base.filter(store__isnull=True)

    if null_store_qs.exists():
        return null_store_qs

    return store_qs


def _require_batch_cost(batch: StockBatch) -> Decimal:

    raw = getattr(batch, "unit_cost", None)

    if raw is None:
        return Decimal("0.00")

    unit_cost = Decimal(str(raw))

    if unit_cost < Decimal("0.00"):
        raise ValueError("unit_cost must be >= 0")

    return unit_cost


@transaction.atomic
def deduct_stock_fifo(*, product, quantity, user=None, sale=None, store=None):

    if not product:
        raise ValueError("product is required")

    if sale is None:
        raise ValueError("sale reference required")

    qty = _to_int_qty(quantity)

    if qty <= 0:
        return {"movements": [], "total_cost": Decimal("0.00")}

    store_id = _resolve_store_id(product=product, store=store)

    today = timezone.localdate()

    remaining_qty = qty

    movements = []

    total_cost = Decimal("0.00")

    batches_qs = (
        _get_batches_qs(product=product, store_id=store_id, today=today)
        .select_for_update()
        .order_by("expiry_date", "created_at", "id")
    )

    batch_list = list(batches_qs)

    total_available = sum(int(b.quantity_remaining or 0) for b in batch_list)

    if total_available < remaining_qty:
        raise InsufficientStockError(
            f"Insufficient stock. Requested {qty}, Available {total_available}"
        )

    for batch in batch_list:

        if remaining_qty <= 0:
            break

        available = int(batch.quantity_remaining or 0)

        if available <= 0:
            continue

        consumed = available if available <= remaining_qty else remaining_qty

        unit_cost = _require_batch_cost(batch)

        batch.quantity_remaining = available - consumed
        batch.is_active = batch.quantity_remaining > 0

        batch.save(update_fields=["quantity_remaining", "is_active"])

        movement = StockMovement.objects.create(
            product=product,
            batch=batch,
            movement_type=StockMovement.MovementType.OUT,
            reason=StockMovement.Reason.SALE,
            quantity=consumed,
            unit_cost_snapshot=unit_cost,
            performed_by=user,
            sale=sale,
        )

        publish(
            StockDeducted(
                product_id=product.id,
                batch_id=batch.id,
                quantity=consumed,
            )
        )

        movements.append(movement)

        total_cost += unit_cost * Decimal(consumed)

        remaining_qty -= consumed

    return {
        "movements": movements,
        "total_cost": total_cost,
    }


@transaction.atomic
def restore_stock_from_sale(*, sale, user=None, items=None):

    sale_movement_list = list(
        StockMovement.objects.select_for_update()
        .filter(
            sale=sale,
            reason=StockMovement.Reason.SALE,
            movement_type=StockMovement.MovementType.OUT,
        )
        .select_related("batch", "product")
        .order_by("created_at", "id")
    )

    if not sale_movement_list:
        raise StockRestorationError("No sale movements")

    created = []

    for sale_mv in sale_movement_list:

        batch = StockBatch.objects.select_for_update().get(
            pk=sale_mv.batch_id
        )

        restore_qty = int(sale_mv.quantity)

        batch.quantity_remaining = (
            int(batch.quantity_remaining or 0) + restore_qty
        )

        batch.is_active = batch.quantity_remaining > 0

        batch.save(update_fields=["quantity_remaining", "is_active"])

        mv = StockMovement.objects.create(
            product=sale_mv.product,
            batch=batch,
            movement_type=StockMovement.MovementType.IN,
            reason=StockMovement.Reason.REFUND,
            quantity=restore_qty,
            unit_cost_snapshot=sale_mv.unit_cost_snapshot,
            performed_by=user,
            sale=sale,
        )

        publish(
            StockRestored(
                product_id=sale_mv.product_id,
                batch_id=batch.id,
                quantity=restore_qty,
            )
        )

        created.append(mv)

    return created