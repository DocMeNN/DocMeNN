# store/services/purchase_service.py

from backend.events.event_bus import publish
from backend.events.domain.purchase_events import GoodsReceived


def receive_goods(invoice):

    invoice.status = "received"
    invoice.save(update_fields=["status"])

    publish(
        GoodsReceived(
            invoice_id=invoice.id,
            supplier_id=invoice.supplier_id,
            total_amount=invoice.total_amount,
        )
    )