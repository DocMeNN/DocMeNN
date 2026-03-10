"""
PATH: backend/events/domain/inventory_events.py

INVENTORY DOMAIN EVENTS
"""

from backend.events.base_event import BaseEvent


class StockDeducted(BaseEvent):
    """
    Fired when stock is deducted (sale / usage).
    """

    def __init__(self, product_id, batch_id, quantity):
        super().__init__()
        self.product_id = product_id
        self.batch_id = batch_id
        self.quantity = quantity


class StockRestored(BaseEvent):
    """
    Fired when stock is restored (refund / cancellation).
    """

    def __init__(self, product_id, batch_id, quantity):
        super().__init__()
        self.product_id = product_id
        self.batch_id = batch_id
        self.quantity = quantity


class StockAdjusted(BaseEvent):
    """
    Fired when stock is manually adjusted.
    """

    def __init__(self, product_id, batch_id, quantity_delta):
        super().__init__()
        self.product_id = product_id
        self.batch_id = batch_id
        self.quantity_delta = quantity_delta