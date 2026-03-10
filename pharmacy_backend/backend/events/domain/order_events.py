"""
PATH: backend/events/domain/order_events.py

ORDER DOMAIN EVENTS
"""

from backend.events.base_event import BaseEvent


class OrderCompleted(BaseEvent):
    """
    Fired when an order is successfully completed.
    """

    def __init__(self, sale_id, user_id, total_amount):
        super().__init__()
        self.sale_id = sale_id
        self.user_id = user_id
        self.total_amount = total_amount


class OrderCancelled(BaseEvent):
    """
    Fired when an order is cancelled.
    """

    def __init__(self, sale_id, user_id):
        super().__init__()
        self.sale_id = sale_id
        self.user_id = user_id