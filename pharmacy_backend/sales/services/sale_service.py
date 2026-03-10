# sales/services/sale_service.py

from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from products.services.stock_fifo import (
    InsufficientStockError,
    deduct_stock_fifo,
)

from sales.models import Sale, SaleItem

from accounting.services.posting import post_sale_to_ledger

from backend.events.event_bus import publish
from backend.events.domain.order_events import OrderCompleted
from backend.events.domain.inventory_events import StockDeducted


class EmptyCartError(Exception):
    pass


class StockValidationError(Exception):
    pass


@transaction.atomic
def create_sale_from_cart(
    *,
    user,
    cart,
    payment_method: str = "cash",
):
    """
    CORE SALES DOMAIN SERVICE
    """

    if not cart or not cart.items.exists():
        raise EmptyCartError("Cart is empty")

    cart_items = cart.items.select_related("product").select_for_update()

    sale = Sale.objects.create(
        user=user,
        payment_method=(payment_method or "cash").lower(),
        status=Sale.STATUS_COMPLETED,
        subtotal_amount=Decimal("0.00"),
        total_amount=Decimal("0.00"),
    )

    subtotal = Decimal("0.00")

    try:

        for item in cart_items:

            sale_item = SaleItem.objects.create(
                sale=sale,
                product=item.product,
                quantity=int(item.quantity),
                unit_price=item.unit_price,
            )

            subtotal += sale_item.total_price

            result = deduct_stock_fifo(
                product=item.product,
                quantity=item.quantity,
                user=user,
                sale=sale,
            )

            publish(
                StockDeducted(
                    sale_id=sale.id,
                    product_id=item.product.id,
                    quantity=item.quantity,
                    total_cost=result["total_cost"],
                )
            )

    except InsufficientStockError as exc:
        transaction.set_rollback(True)
        raise StockValidationError(str(exc))

    tax = getattr(sale, "tax_amount", Decimal("0.00")) or Decimal("0.00")
    discount = getattr(sale, "discount_amount", Decimal("0.00")) or Decimal("0.00")

    sale.subtotal_amount = subtotal
    sale.total_amount = subtotal + tax - discount
    sale.completed_at = timezone.now()

    sale.save(
        update_fields=[
            "subtotal_amount",
            "total_amount",
            "completed_at",
        ]
    )

    try:
        post_sale_to_ledger(sale=sale)
    except Exception as exc:
        transaction.set_rollback(True)
        raise RuntimeError(f"Ledger posting failed: {exc}") from exc

    publish(
        OrderCompleted(
            sale_id=sale.id,
            user_id=user.id,
            total_amount=sale.total_amount,
        )
    )

    cart.items.all().delete()
    cart.is_active = False
    cart.save(update_fields=["is_active"])

    return sale