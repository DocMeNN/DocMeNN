"""
PATH: backend/events/event_bus.py

EVENT BUS + OUTBOX PERSISTENCE + DISPATCHER

Responsibilities
- register event handlers
- persist events to the outbox
- dispatch events to handlers
- process stored outbox events
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Callable, Dict, List, Type

from django.utils import timezone

from backend.events.base_event import BaseEvent
from backend.events.models import EventOutbox

logger = logging.getLogger(__name__)


# -----------------------------------------------------
# Handler registry
# -----------------------------------------------------

_handlers: Dict[Type[BaseEvent], List[Callable]] = defaultdict(list)

# event_type string → event class
_event_registry: Dict[str, Type[BaseEvent]] = {}


def _event_name(event_class: Type[BaseEvent]) -> str:
    """
    Resolve event name.

    Uses class name as canonical event type.
    """
    return event_class.__name__


def register(event_type: Type[BaseEvent], handler: Callable) -> None:
    """
    Register an event handler for a specific event type.
    """

    if handler not in _handlers[event_type]:
        _handlers[event_type].append(handler)

    event_name = _event_name(event_type)

    _event_registry[event_name] = event_type


# -----------------------------------------------------
# Publish
# -----------------------------------------------------

def publish(event: BaseEvent) -> None:
    """
    Persist event to the outbox.
    """

    EventOutbox.objects.create(
        event_type=event.__class__.__name__,
        payload=event.to_dict(),
    )


# -----------------------------------------------------
# Immediate dispatch
# -----------------------------------------------------

def dispatch(event: BaseEvent) -> None:
    """
    Dispatch in-memory event.
    """

    handlers = _handlers.get(type(event), [])

    for handler in handlers:
        try:
            handler(event)

        except Exception:
            logger.exception(
                "Event handler failed",
                extra={
                    "event_type": event.__class__.__name__,
                    "handler": handler.__name__,
                },
            )


# -----------------------------------------------------
# Outbox processor
# -----------------------------------------------------

def process_outbox(batch_size: int = 100) -> int:
    """
    Process pending events from the outbox.
    """

    events = (
        EventOutbox.objects
        .filter(processed=False)
        .order_by("created_at")[:batch_size]
    )

    processed_count = 0

    for record in events:

        try:

            event_class = _event_registry.get(record.event_type)

            if not event_class:
                logger.warning(
                    "No event class registered",
                    extra={"event_type": record.event_type},
                )
                continue

            handlers = _handlers.get(event_class, [])

            for handler in handlers:

                try:
                    handler(record.payload)

                except Exception:
                    logger.exception(
                        "Event handler failed during outbox processing",
                        extra={
                            "event_type": record.event_type,
                            "handler": handler.__name__,
                        },
                    )

            record.processed = True
            record.processed_at = timezone.now()
            record.save(update_fields=["processed", "processed_at"])

            processed_count += 1

        except Exception:
            logger.exception(
                "Failed processing outbox event",
                extra={
                    "event_id": str(record.id),
                    "event_type": record.event_type,
                },
            )

    return processed_count