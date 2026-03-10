"""
PATH: backend/events/domain/payment_events.py

PAYMENT DOMAIN EVENTS
"""

from backend.events.base_event import BaseEvent


class PaymentCompleted(BaseEvent):
    """
    Fired when a payment succeeds.
    """

    def __init__(self, payment_id, order_id, amount):
        super().__init__()
        self.payment_id = payment_id
        self.order_id = order_id
        self.amount = amount


class PaymentFailed(BaseEvent):
    """
    Fired when a payment fails.
    """

    def __init__(self, payment_id, order_id, amount):
        super().__init__()
        self.payment_id = payment_id
        self.order_id = order_id
        self.amount = amount