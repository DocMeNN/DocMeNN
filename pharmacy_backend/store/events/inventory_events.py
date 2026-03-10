from backend.events.base_event import BaseEvent


class InventoryUpdatedEvent(BaseEvent):

    def __init__(self, product_id, quantity):
        super().__init__()
        self.product_id = product_id
        self.quantity = quantity