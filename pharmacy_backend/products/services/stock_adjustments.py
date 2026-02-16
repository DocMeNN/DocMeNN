# products/services/stock_adjustments.py

"""
STOCK ADJUSTMENTS SERVICE (PHASE 2.2)

Purpose:
- Perform controlled stock adjustments on a specific StockBatch.
- Enforce auditability via immutable StockMovement rows.
- Keep StockBatch.quantity_remaining service-managed only.

Rules:
- quantity_delta must be a non-zero integer
- adjustment cannot reduce remaining below zero
- creates StockMovement(reason=ADJUSTMENT) with movement_type based on delta
"""

from __future__ import annotations

from dataclasses import dataclass

from django.db import transaction
from django.core.exceptions import ValidationError

from products.models import StockBatch, StockMovement


class StockAdjustmentError(Exception):
    """Domain error for adjustment failures."""


@dataclass(frozen=True)
class AdjustmentResult:
    batch: StockBatch
    movement: StockMovement
    quantity_delta: int


def _to_int_delta(value) -> int:
    if value is None or value == "":
        raise StockAdjustmentError("quantity_delta is required")

    if isinstance(value, bool):
        # guardrail: bool is an int subclass in Python
        raise StockAdjustmentError("quantity_delta must be an integer")

    try:
        delta = int(value)
    except (TypeError, ValueError):
        raise StockAdjustmentError("quantity_delta must be an integer")

    if delta == 0:
        raise StockAdjustmentError("quantity_delta cannot be 0")

    return delta


@transaction.atomic
def adjust_stock_batch(
    *,
    batch: StockBatch,
    quantity_delta,
    user=None,
    note: str = "",
) -> AdjustmentResult:
    """
    Adjust a batch up or down with an immutable audit movement.

    quantity_delta:
      +N -> IN adjustment (adds to remaining)
      -N -> OUT adjustment (removes from remaining)
    """
    if batch is None:
        raise StockAdjustmentError("batch is required")

    # lock row for concurrency safety
    locked_batch = StockBatch.objects.select_for_update().get(pk=batch.pk)

    delta = _to_int_delta(quantity_delta)

    current_remaining = int(locked_batch.quantity_remaining or 0)

    if delta < 0:
        abs_out = abs(delta)
        if abs_out > current_remaining:
            raise StockAdjustmentError(
                f"Cannot reduce stock below zero. Remaining: {current_remaining}, Requested OUT: {abs_out}"
            )

        locked_batch.quantity_remaining = current_remaining - abs_out
        movement_type = StockMovement.MovementType.OUT
        qty = abs_out
    else:
        locked_batch.quantity_remaining = current_remaining + delta
        movement_type = StockMovement.MovementType.IN
        qty = delta

    # Save batch (model derives is_active and validates invariants)
    try:
        locked_batch.save()
    except ValidationError as exc:
        raise StockAdjustmentError(str(exc)) from exc

    # Create movement (append-only audit row)
    movement = StockMovement.objects.create(
        product=locked_batch.product,
        batch=locked_batch,
        movement_type=movement_type,
        reason=StockMovement.Reason.ADJUSTMENT,
        quantity=qty,
        performed_by=user,
        sale=None,
    )

    # NOTE: if you later add an "audit note" field to StockMovement,
    # you can store `note` there. For now we keep note unused.

    return AdjustmentResult(
        batch=locked_batch,
        movement=movement,
        quantity_delta=delta,
    )
