"""
PATH: backend/events/domain/refund_events.py

REFUND DOMAIN EVENTS
"""

from backend.events.base_event import BaseEvent


class RefundCompleted(BaseEvent):
    """
    Fired when a refund is processed.
    """

    def __init__(self, sale_id, refund_id, total_amount):
        super().__init__()
        self.sale_id = sale_id
        self.refund_id = refund_id
        self.total_amount = total_amount