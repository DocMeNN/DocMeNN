# accounting/management/commands/reset_pilot_data.py

from django.core.management.base import BaseCommand
from django.db import transaction

from sales.models import (
    Sale,
    SaleItem,
    SaleItemRefund,
    SaleRefundAudit,
    SalePaymentAllocation,
)

from accounting.models.event import AccountingEvent
from accounting.models.journal import JournalEntry
from accounting.models.ledger import LedgerEntry


class Command(BaseCommand):
    help = "Reset all transactional ERP data for pilot/testing (keeps master data)."

    @transaction.atomic
    def handle(self, *args, **kwargs):

        self.stdout.write(self.style.WARNING("\nStarting PILOT DATA RESET...\n"))

        counts = {
            "sales": Sale.objects.count(),
            "sale_items": SaleItem.objects.count(),
            "sale_item_refunds": SaleItemRefund.objects.count(),
            "sale_refund_audits": SaleRefundAudit.objects.count(),
            "payments": SalePaymentAllocation.objects.count(),
            "accounting_events": AccountingEvent.objects.count(),
            "ledger_entries": LedgerEntry.objects.count(),
            "journal_entries": JournalEntry.objects.count(),
        }

        self.stdout.write("Current database state:")
        for k, v in counts.items():
            self.stdout.write(f"{k}: {v}")

        self.stdout.write("\nClearing transactional tables...\n")

        # deepest dependencies first
        SaleItemRefund.objects.all().delete()
        SaleRefundAudit.objects.all().delete()
        SalePaymentAllocation.objects.all().delete()

        # sales engine
        SaleItem.objects.all().delete()
        Sale.objects.all().delete()

        # accounting engine
        AccountingEvent.objects.all().delete()

        # immutable accounting tables require raw delete
        LedgerEntry.objects.all()._raw_delete(LedgerEntry.objects.db)
        JournalEntry.objects.all()._raw_delete(JournalEntry.objects.db)

        self.stdout.write(
            self.style.SUCCESS(
                "\nPILOT DATA RESET COMPLETE\n"
                "All transactional data cleared.\n"
                "Master data preserved.\n"
            )
        )

        self.stdout.write("Verifying clean state...\n")

        self.stdout.write(f"Sales: {Sale.objects.count()}")
        self.stdout.write(f"SaleItems: {SaleItem.objects.count()}")
        self.stdout.write(f"AccountingEvents: {AccountingEvent.objects.count()}")
        self.stdout.write(f"LedgerEntries: {LedgerEntry.objects.count()}")
        self.stdout.write(f"JournalEntries: {JournalEntry.objects.count()}")

        self.stdout.write(self.style.SUCCESS("\nSystem is now financially clean.\n"))