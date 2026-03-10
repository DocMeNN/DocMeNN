# store/services/inventory_service.py

from backend.events.event_bus import publish
from backend.events.domain.inventory_events import StockAdjusted

from store.models import Product


def adjust_stock(product: Product, batch_id: str, quantity_delta: int):

    product.stock_quantity += quantity_delta
    product.save(update_fields=["stock_quantity"])

    publish(
        StockAdjusted(
            product_id=product.id,
            batch_id=batch_id,
            quantity_delta=quantity_delta,
        )
    )