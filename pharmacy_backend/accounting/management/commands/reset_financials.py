# accounting/management/commands/reset_financials.py

from django.core.management.base import BaseCommand
from django.db import transaction

from accounting.models.journal import JournalEntry


class Command(BaseCommand):
    help = "Reset all journal entries to zero while keeping chart of accounts"

    @transaction.atomic
    def handle(self, *args, **kwargs):

        self.stdout.write(self.style.WARNING("Resetting financial transactions..."))

        entry_count = JournalEntry.objects.count()

        JournalEntry.objects.all().delete()

        self.stdout.write(
            self.style.SUCCESS(
                f"Financial reset complete.\n"
                f"Deleted {entry_count} journal entries.\n"
                f"Chart of accounts preserved."
            )
        )