"""
PATH: backend/events/domain/purchase_events.py

PURCHASE DOMAIN EVENTS
"""

from backend.events.base_event import BaseEvent


class GoodsReceived(BaseEvent):
    """
    Fired when purchased goods arrive and are stocked.
    """

    def __init__(self, invoice_id, supplier_id, total_amount):
        super().__init__()
        self.invoice_id = invoice_id
        self.supplier_id = supplier_id
        self.total_amount = total_amount