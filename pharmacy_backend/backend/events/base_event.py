"""
======================================================
PATH: backend/events/base_event.py
======================================================

BASE DOMAIN EVENT

Every domain event in the system inherits from BaseEvent.

Responsibilities:
- Provide timestamp
- Provide unique event_id
- Provide event_type
- Convert event → dictionary payload
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class BaseEvent:
    """
    Base class for all domain events.
    """

    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    event_type: str = field(init=False)
    occurred_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def __post_init__(self):
        self.event_type = self.__class__.__name__

    def to_dict(self) -> dict:
        """
        Convert event to serializable dictionary.
        """

        payload = self.__dict__.copy()

        payload["occurred_at"] = self.occurred_at.isoformat()

        return payload