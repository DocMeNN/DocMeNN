# ============================================================
# PATH: accounting/services/event_processor.py
# ============================================================

from decimal import Decimal
from django.db import transaction

from accounting.models.event import AccountingEvent
from accounting.models.journal import JournalEntry
from accounting.models.ledger import LedgerEntry
from accounting.models.account import Account


class AccountingEventProcessor:
    """
    Converts AccountingEvents into JournalEntries + LedgerEntries.

    Designed for:
    - async processing
    - replayable accounting
    - event-based financial architecture
    """

    # ----------------------------------------------------------

    @staticmethod
    def process_event(event: AccountingEvent):

        if event.processing_status != AccountingEvent.PROCESSING_PENDING:
            return

        try:
            if event.event_type == AccountingEvent.EVENT_SALE_COMPLETED:
                AccountingEventProcessor._process_sale_completed(event)

            else:
                raise ValueError(f"Unsupported event type {event.event_type}")

            event.mark_processed()

        except Exception as exc:
            event.mark_failed(str(exc))
            raise

    # ----------------------------------------------------------

    @staticmethod
    @transaction.atomic
    def _process_sale_completed(event: AccountingEvent):

        from sales.models.sale import Sale

        sale = Sale.objects.get(id=event.source_id)

        # Example account lookup
        # (replace with your real chart codes later)

        cash_account = Account.objects.get(code="1000")
        revenue_account = Account.objects.get(code="4000")
        cogs_account = Account.objects.get(code="5000")
        inventory_account = Account.objects.get(code="1200")

        journal = JournalEntry.objects.create(
            store=sale.store,
            reference=str(sale.id),
            source_module="POS",
            description=f"Sale {sale.invoice_no}",
            created_by=sale.user,
        )

        # -----------------------------------
        # Revenue
        # -----------------------------------

        LedgerEntry.objects.create(
            journal_entry=journal,
            account=cash_account,
            entry_type=LedgerEntry.DEBIT,
            amount=sale.total_amount,
        )

        LedgerEntry.objects.create(
            journal_entry=journal,
            account=revenue_account,
            entry_type=LedgerEntry.CREDIT,
            amount=sale.subtotal_amount,
        )

        # -----------------------------------
        # COGS
        # -----------------------------------

        if sale.cogs_amount and sale.cogs_amount > Decimal("0"):

            LedgerEntry.objects.create(
                journal_entry=journal,
                account=cogs_account,
                entry_type=LedgerEntry.DEBIT,
                amount=sale.cogs_amount,
            )

            LedgerEntry.objects.create(
                journal_entry=journal,
                account=inventory_account,
                entry_type=LedgerEntry.CREDIT,
                amount=sale.cogs_amount,
            )

    # ----------------------------------------------------------

    @staticmethod
    def process_pending_events(limit=100):

        events = AccountingEvent.objects.filter(
            processing_status=AccountingEvent.PROCESSING_PENDING
        ).order_by("created_at")[:limit]

        for event in events:
            AccountingEventProcessor.process_event(event)