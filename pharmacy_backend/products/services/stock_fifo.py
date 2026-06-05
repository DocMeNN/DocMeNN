# pharmacy_backend/products/services/stock_fifo.py

from django.db import transaction
from django.utils import timezone

from products.models import StockBatch, StockMovement


class InsufficientStockError(Exception):
    """
    Raised when available stock cannot fulfill requested quantity.
    """
    pass


@transaction.atomic
def deduct_stock_fifo(*, product, quantity, user=None, sale=None):
    """
    Deduct stock using FIFO (First-Expiry-First-Out) and
    record immutable stock movement audit entries.

    PARAMS:
    - product (Product)
    - quantity (int)
    - user (User | None)
    - sale (Sale | None)

    RETURNS:
    - List[StockMovement]
    """

    if not product:
        raise ValueError("Product is required")

    if quantity <= 0:
        return []

    today = timezone.now().date()
    remaining_qty = quantity
    movements = []

    batches = (
        StockBatch.objects
        .select_for_update()
        .filter(
            product=product,
            is_active=True,
            expiry_date__gte=today,
            quantity_remaining__gt=0,
        )
        .order_by("expiry_date", "created_at")
    )

    total_available = sum(batch.quantity_remaining for batch in batches)

    if total_available < remaining_qty:
        raise InsufficientStockError(
            f"Insufficient stock for {product.name}. "
            f"Requested: {quantity}, Available: {total_available}"
        )

    for batch in batches:
        if remaining_qty <= 0:
            break

        if batch.quantity_remaining <= remaining_qty:
            consumed = batch.quantity_remaining
            remaining_qty -= consumed
            batch.quantity_remaining = 0
            batch.is_active = False
        else:
            consumed = remaining_qty
            batch.quantity_remaining -= consumed
            remaining_qty = 0

        batch.save()

        movement = StockMovement.objects.create(
            product=product,
            batch=batch,
            movement_type=StockMovement.MovementType.OUT,
            reason=StockMovement.Reason.SALE,
            quantity=consumed,
            performed_by=user,
            sale_id=sale.id if sale else None,
        )

        movements.append(movement)

    return movements
