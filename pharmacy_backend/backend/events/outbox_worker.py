"""
PATH: backend/events/outbox_worker.py

Processes pending outbox events.
"""

import logging

from django.utils import timezone

from backend.events.base_event import BaseEvent
from backend.events.event_bus import dispatch
from backend.events.models import EventOutbox

logger = logging.getLogger(__name__)


def process_outbox(batch_size: int = 100):

    events = (
        EventOutbox.objects
        .filter(processed=False)
        .order_by("created_at")[:batch_size]
    )

    for record in events:

        try:

            event = BaseEvent()
            event.__dict__.update(record.payload)

            dispatch(event)

            record.processed = True
            record.processed_at = timezone.now()
            record.save(update_fields=["processed", "processed_at"])

        except Exception:

            logger.exception(
                "Outbox event failed",
                extra={"event_id": str(record.id)},
            )