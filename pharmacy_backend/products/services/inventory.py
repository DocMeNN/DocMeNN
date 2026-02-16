# products/services/inventory.py

"""
======================================================
PATH: products/services/inventory.py
======================================================
INVENTORY CORE SERVICES (PHASE 2)

Purpose:
- Canonical stock intake: create StockBatch + create RECEIPT movement (profit-ready).
- Legacy repair: receive_stock() exists ONLY to backfill missing receipt movements.
- Adjust stock after receipt with full audit movements.
- Expire remaining stock in a batch (idempotent, auditable).

Rules:
- Quantities are integer units (StockMovement.quantity is PositiveIntegerField).
- StockBatch derives is_active from quantity_remaining (model-enforced).
- All movements created here MUST include unit_cost_snapshot when cost exists.

HOTSPRINT:
- COGS depends on StockMovement.unit_cost_snapshot (never invent cost).
"""

from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.core.exceptions import ValidationError

from products.models.stock_batch import StockBatch
from products.models.stock_movement import StockMovement


def _require_batch(batch: StockBatch) -> None:
    if not batch or not getattr(batch, "id", None):
        raise ValidationError("batch is required")


def _to_int(value, *, field_name="value") -> int:
    if value is None or value == "":
        raise ValidationError(f"{field_name} is required")
    if isinstance(value, bool):
        raise ValidationError(f"{field_name} must be an integer")
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValidationError(f"{field_name} must be an integer")


def _to_decimal(value, *, field_name="value") -> Decimal:
    if value is None or value == "" or value == "null":
        raise ValidationError(f"{field_name} is required")
    try:
        return Decimal(str(value))
    except Exception as exc:
        raise ValidationError(f"{field_name} must be a valid decimal") from exc


def _has_receipt_movement(batch: StockBatch) -> bool:
    return StockMovement.objects.filter(
        batch=batch,
        reason=StockMovement.Reason.RECEIPT,
        movement_type=StockMovement.MovementType.IN,
    ).exists()


def _require_unit_cost(batch: StockBatch) -> Decimal:
    raw = getattr(batch, "unit_cost", None)
    if raw in (None, "", "null"):
        raise ValidationError(
            "StockBatch.unit_cost is required for inventory movements. "
            "Backfill legacy batches before using inventory services."
        )
    try:
        cost = Decimal(str(raw))
    except Exception as exc:
        raise ValidationError("StockBatch.unit_cost must be a valid decimal") from exc
    if cost <= Decimal("0.00"):
        raise ValidationError("StockBatch.unit_cost must be greater than zero")
    return cost


def _require_positive_int(value: int, *, field_name: str) -> int:
    v = _to_int(value, field_name=field_name)
    if v <= 0:
        raise ValidationError(f"{field_name} must be greater than zero")
    return v


def _require_positive_cost(cost: Decimal) -> Decimal:
    if cost <= Decimal("0.00"):
        raise ValidationError("unit_cost must be greater than zero")
    return cost


@transaction.atomic
def intake_stock(
    *,
    product,
    batch_number: str,
    expiry_date,
    quantity_received: int,
    unit_cost,
    user=None,
) -> StockBatch:
    """
    CANONICAL STOCK INTAKE (new flow)

    Creates:
    - StockBatch (quantity_remaining initialized to quantity_received)
    - RECEIPT StockMovement (unit_cost_snapshot stamped)

    Idempotency/guard:
    - If a matching batch exists (same product+batch_number), we lock it and:
        - If receipt movement exists: return it (idempotent)
        - Else: create missing receipt + ensure remaining initialized
    """
    bn = (batch_number or "").strip()
    if not bn:
        raise ValidationError("batch_number is required")

    if not expiry_date:
        raise ValidationError("expiry_date is required")

    qty = _require_positive_int(quantity_received, field_name="quantity_received")
    cost = _require_positive_cost(_to_decimal(unit_cost, field_name="unit_cost"))

    # Prefer idempotent reuse when caller repeats same intake.
    existing = (
        StockBatch.objects.select_for_update()
        .filter(product=product, batch_number=bn)
        .first()
    )

    if existing:
        # Ensure unit_cost is present (do not overwrite non-null blindly).
        if getattr(existing, "unit_cost", None) in (None, "", "null"):
            existing.unit_cost = cost
            existing.save(update_fields=["unit_cost"])

        if not _has_receipt_movement(existing):
            if int(existing.quantity_remaining or 0) <= 0:
                existing.quantity_remaining = int(existing.quantity_received or qty)
                existing.save(update_fields=["quantity_remaining", "is_active"])

            StockMovement.objects.create(
                product=existing.product,
                batch=existing,
                movement_type=StockMovement.MovementType.IN,
                reason=StockMovement.Reason.RECEIPT,
                quantity=int(existing.quantity_received or qty),
                unit_cost_snapshot=_require_unit_cost(existing),
                performed_by=user,
            )

        return existing

    # Create new batch + receipt movement in one go
    batch = StockBatch.objects.create(
        product=product,
        batch_number=bn,
        expiry_date=expiry_date,
        unit_cost=cost,
        quantity_received=qty,
        quantity_remaining=qty,
    )

    StockMovement.objects.create(
        product=batch.product,
        batch=batch,
        movement_type=StockMovement.MovementType.IN,
        reason=StockMovement.Reason.RECEIPT,
        quantity=qty,
        unit_cost_snapshot=cost,
        performed_by=user,
    )

    return batch


@transaction.atomic
def receive_stock(*, batch: StockBatch, user=None) -> StockBatch:
    """
    LEGACY receipt fixer (backward compatibility).

    Why it exists:
    - Older data may contain StockBatch rows without a RECEIPT StockMovement.
    - New purchase-led flow should use intake_stock().

    Behavior:
    - If receipt movement exists -> return batch (idempotent).
    - Else -> initialize remaining quantity ONLY (no double counting),
      then create the missing RECEIPT movement ONCE.
    """
    _require_batch(batch)
    batch = StockBatch.objects.select_for_update().get(id=batch.id)

    if int(batch.quantity_received or 0) <= 0:
        raise ValidationError("quantity_received must be greater than zero")

    unit_cost = _require_unit_cost(batch)

    if _has_receipt_movement(batch):
        return batch

    # Initialize remaining if it looks unreceived
    if int(batch.quantity_remaining or 0) <= 0:
        batch.quantity_remaining = int(batch.quantity_received or 0)
        batch.save(update_fields=["quantity_remaining", "is_active"])

    # Create the missing receipt movement (once)
    StockMovement.objects.create(
        product=batch.product,
        batch=batch,
        movement_type=StockMovement.MovementType.IN,
        reason=StockMovement.Reason.RECEIPT,
        quantity=int(batch.quantity_received or 0),
        unit_cost_snapshot=unit_cost,
        performed_by=user,
    )

    return batch


@transaction.atomic
def adjust_stock(*, batch: StockBatch, quantity_delta: int, user=None) -> StockBatch:
    _require_batch(batch)

    delta = _to_int(quantity_delta, field_name="quantity_delta")
    if delta == 0:
        raise ValidationError("quantity_delta cannot be 0")

    batch = StockBatch.objects.select_for_update().get(id=batch.id)
    unit_cost = _require_unit_cost(batch)

    if not _has_receipt_movement(batch):
        raise ValidationError("Cannot adjust stock before batch is received (missing RECEIPT movement)")

    current = int(batch.quantity_remaining or 0)
    new_quantity = current + delta
    if new_quantity < 0:
        raise ValidationError(
            f"Stock adjustment would result in negative stock. Remaining={current}, delta={delta}"
        )

    batch.quantity_remaining = new_quantity
    batch.save(update_fields=["quantity_remaining", "is_active"])

    StockMovement.objects.create(
        product=batch.product,
        batch=batch,
        movement_type=(StockMovement.MovementType.IN if delta > 0 else StockMovement.MovementType.OUT),
        reason=StockMovement.Reason.ADJUSTMENT,
        quantity=abs(delta),
        unit_cost_snapshot=unit_cost,
        performed_by=user,
    )

    return batch


@transaction.atomic
def expire_stock(*, batch: StockBatch, user=None) -> StockBatch:
    _require_batch(batch)

    batch = StockBatch.objects.select_for_update().get(id=batch.id)
    remaining = int(batch.quantity_remaining or 0)
    if remaining <= 0:
        return batch

    unit_cost = _require_unit_cost(batch)

    if not _has_receipt_movement(batch):
        raise ValidationError("Cannot expire stock before batch is received (missing RECEIPT movement)")

    expired_qty = remaining
    batch.quantity_remaining = 0
    batch.save(update_fields=["quantity_remaining", "is_active"])

    StockMovement.objects.create(
        product=batch.product,
        batch=batch,
        movement_type=StockMovement.MovementType.OUT,
        reason=StockMovement.Reason.EXPIRY,
        quantity=expired_qty,
        unit_cost_snapshot=unit_cost,
        performed_by=user,
    )

    return batch
