from backend.events.base_event import BaseEvent


class OrderPlacedEvent(BaseEvent):

    def __init__(self, order_id, user_id):
        super().__init__()
        self.order_id = order_id
        self.user_id = user_id