# store/services/refund_service.py

from backend.events.event_bus import publish
from backend.events.domain.refund_events import RefundCompleted


def process_refund(refund):

    refund.status = "completed"
    refund.save(update_fields=["status"])

    publish(
        RefundCompleted(
            sale_id=refund.sale_id,
            refund_id=refund.id,
            total_amount=refund.total_amount,
        )
    )