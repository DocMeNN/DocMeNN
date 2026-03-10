"""
PATH: backend/events/management/commands/run_event_worker.py

EVENT OUTBOX WORKER

Continuously processes events stored in the EventOutbox table.

This worker:
- polls the outbox
- dispatches events to handlers
- marks events as processed

Usage:

    python manage.py run_event_worker

Optional:

    python manage.py run_event_worker --interval 2
"""

from __future__ import annotations

import time
import logging

from django.core.management.base import BaseCommand

from backend.events.event_bus import process_outbox

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Run the event outbox worker"

    def add_arguments(self, parser):

        parser.add_argument(
            "--interval",
            type=float,
            default=1.0,
            help="Polling interval in seconds (default: 1.0)",
        )

        parser.add_argument(
            "--batch-size",
            type=int,
            default=100,
            help="Number of events processed per cycle",
        )

    def handle(self, *args, **options):

        interval = options["interval"]
        batch_size = options["batch_size"]

        self.stdout.write(self.style.SUCCESS("Event worker started"))

        while True:

            try:

                processed = process_outbox(batch_size=batch_size)

                if processed:
                    logger.info(
                        "Processed outbox events",
                        extra={"count": processed},
                    )

                time.sleep(interval)

            except KeyboardInterrupt:

                self.stdout.write(
                    self.style.WARNING("Event worker stopped")
                )

                break

            except Exception:

                logger.exception("Event worker crashed")

                time.sleep(interval)