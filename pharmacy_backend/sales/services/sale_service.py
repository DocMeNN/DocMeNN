# sales/services/sale_service.py

from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from products.services.stock_fifo import (
    InsufficientStockError,
    deduct_stock_fifo,
)
from sales.models import Sale, SaleItem


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

    SINGLE SOURCE OF TRUTH for:
    - Sale creation
    - SaleItem creation
    - FIFO stock deduction
    - Totals calculation

    GUARANTEES:
    - FIFO is the ONLY stock authority
    - No pre-validation outside FIFO
    - Fully atomic checkout
    """

    if not cart.items.exists():
        raise EmptyCartError("Cart is empty")

    cart_items = cart.items.select_related("product").select_for_update()

    # --------------------------------------------------
    # CREATE SALE (DRAFT STATE)
    # --------------------------------------------------
    sale = Sale.objects.create(
        user=user,
        payment_method=payment_method.lower(),
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
                quantity=item.quantity,
                unit_price=item.unit_price,  # 🔒 PRICE SNAPSHOT
            )

            subtotal += sale_item.total_price

            # 🔑 SINGLE STOCK EXIT POINT
            deduct_stock_fifo(
                product=item.product,
                quantity=item.quantity,
                user=user,
                sale=sale,
            )

    except InsufficientStockError as exc:
        transaction.set_rollback(True)
        raise StockValidationError(str(exc))

    sale.subtotal_amount = subtotal
    sale.total_amount = subtotal + sale.tax_amount - sale.discount_amount
    sale.completed_at = timezone.now()

    sale.save(
        update_fields=[
            "subtotal_amount",
            "total_amount",
            "completed_at",
        ]
    )

    # --------------------------------------------------
    # FINALIZE CART
    # --------------------------------------------------
    cart.items.all().delete()
    cart.is_active = False
    cart.save(update_fields=["is_active"])

    return sale
