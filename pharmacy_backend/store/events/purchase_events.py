from backend.events.base_event import BaseEvent


class PurchaseCompletedEvent(BaseEvent):

    def __init__(self, purchase_id, user_id):
        super().__init__()
        self.purchase_id = purchase_id
        self.user_id = user_id