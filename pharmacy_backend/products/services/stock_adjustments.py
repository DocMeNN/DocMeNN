"""
STOCK ADJUSTMENTS SERVICE
"""

from __future__ import annotations

from dataclasses import dataclass

from django.core.exceptions import ValidationError
from django.db import transaction

from products.models import StockBatch, StockMovement

from backend.events.event_bus import publish
from backend.events.domain.inventory_events import StockAdjusted


class StockAdjustmentError(Exception):
    pass


@dataclass(frozen=True)
class AdjustmentResult:
    batch: StockBatch
    movement: StockMovement
    quantity_delta: int


def _to_int_delta(value) -> int:

    if value is None or value == "":
        raise StockAdjustmentError("quantity_delta required")

    if isinstance(value, bool):
        raise StockAdjustmentError("must be integer")

    try:
        delta = int(value)
    except (TypeError, ValueError):
        raise StockAdjustmentError("must be integer")

    if delta == 0:
        raise StockAdjustmentError("cannot be 0")

    return delta


@transaction.atomic
def adjust_stock_batch(
    *,
    batch: StockBatch,
    quantity_delta,
    user=None,
    note: str = "",
) -> AdjustmentResult:

    if batch is None:
        raise StockAdjustmentError("batch required")

    locked_batch = StockBatch.objects.select_for_update().get(pk=batch.pk)

    delta = _to_int_delta(quantity_delta)

    current_remaining = int(locked_batch.quantity_remaining or 0)

    if delta < 0:

        abs_out = abs(delta)

        if abs_out > current_remaining:
            raise StockAdjustmentError(
                f"Cannot reduce below zero. Remaining {current_remaining}"
            )

        locked_batch.quantity_remaining = current_remaining - abs_out
        movement_type = StockMovement.MovementType.OUT
        qty = abs_out

    else:

        locked_batch.quantity_remaining = current_remaining + delta
        movement_type = StockMovement.MovementType.IN
        qty = delta

    try:
        locked_batch.save()
    except ValidationError as exc:
        raise StockAdjustmentError(str(exc)) from exc

    movement = StockMovement.objects.create(
        product=locked_batch.product,
        batch=locked_batch,
        movement_type=movement_type,
        reason=StockMovement.Reason.ADJUSTMENT,
        quantity=qty,
        performed_by=user,
        sale=None,
    )

    publish(
        StockAdjusted(
            product_id=locked_batch.product_id,
            batch_id=locked_batch.id,
            quantity_delta=delta,
        )
    )

    return AdjustmentResult(
        batch=locked_batch,
        movement=movement,
        quantity_delta=delta,
    )