"""
PATH: backend/events/management/commands/process_outbox.py
"""

from django.core.management.base import BaseCommand

from backend.events.outbox_worker import process_outbox


class Command(BaseCommand):

    help = "Process event outbox"

    def handle(self, *args, **kwargs):

        process_outbox()

        self.stdout.write(self.style.SUCCESS("Outbox processed"))