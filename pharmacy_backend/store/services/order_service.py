# store/services/order_service.py

from backend.events.event_bus import publish
from backend.events.domain.order_events import OrderCompleted


def complete_order(order):

    order.status = "completed"
    order.save(update_fields=["status"])

    publish(
        OrderCompleted(
            sale_id=order.id,
            user_id=order.user_id,
            total_amount=order.total_amount,
        )
    )