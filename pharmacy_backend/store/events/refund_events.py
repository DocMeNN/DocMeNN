from backend.events.base_event import BaseEvent


class RefundProcessedEvent(BaseEvent):

    def __init__(self, refund_id, order_id):
        super().__init__()
        self.refund_id = refund_id
        self.order_id = order_id