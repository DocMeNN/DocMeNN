# accounting/management/commands/backfill_pos_references.py

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from accounting.models.journal import JournalEntry
from sales.models.sale import Sale
from sales.models.refund_audit import SaleRefundAudit


class Command(BaseCommand):
    help = "Backfill JournalEntry.reference for legacy POS sale/refund journal entries."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would change without saving.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        dry_run = bool(options.get("dry_run"))

        fixed_sales = 0
        skipped_sales = 0
        fixed_refunds = 0
        skipped_refunds = 0

        self.stdout.write("Backfilling POS references...")
        if dry_run:
            self.stdout.write("DRY RUN: no database changes will be saved.\n")

        # -----------------------------
        # SALES
        # -----------------------------
        sales = Sale.objects.filter(status=Sale.STATUS_COMPLETED).only("id", "invoice_no")

        for sale in sales:
            ref = f"POS_SALE:{sale.id}"

            # Already has correct reference?
            if JournalEntry.objects.filter(reference=ref).exists():
                continue

            # Try match by invoice number first (most reliable)
            qs = JournalEntry.objects.filter(reference__isnull=True)
            if sale.invoice_no:
                qs = qs.filter(description__icontains=sale.invoice_no)
            else:
                qs = qs.filter(description__icontains=str(sale.id))

            matches = list(qs.order_by("-posted_at")[:3])

            if len(matches) != 1:
                skipped_sales += 1
                continue

            je = matches[0]
            self.stdout.write(f"SALE  {sale.invoice_no} -> set reference={ref}")

            if not dry_run:
                je.reference = ref
                je.save(update_fields=["reference"])

            fixed_sales += 1

        # -----------------------------
        # REFUNDS
        # -----------------------------
        audits = SaleRefundAudit.objects.all().select_related("sale").only("id", "sale__invoice_no")

        for audit in audits:
            ref = f"POS_REFUND:{audit.id}"

            if JournalEntry.objects.filter(reference=ref).exists():
                continue

            qs = JournalEntry.objects.filter(reference__isnull=True)

            # Refund descriptions are: "POS Refund <invoice_no or id>"
            inv = getattr(audit.sale, "invoice_no", None)
            if inv:
                qs = qs.filter(description__icontains=inv)
            else:
                qs = qs.filter(description__icontains="POS Refund")

            matches = list(qs.order_by("-posted_at")[:3])

            if len(matches) != 1:
                skipped_refunds += 1
                continue

            je = matches[0]
            self.stdout.write(f"REFUND {inv or audit.id} -> set reference={ref}")

            if not dry_run:
                je.reference = ref
                je.save(update_fields=["reference"])

            fixed_refunds += 1

        self.stdout.write("\n--- Summary ---")
        self.stdout.write(f"Sales fixed:   {fixed_sales}")
        self.stdout.write(f"Sales skipped: {skipped_sales} (ambiguous/no match)")
        self.stdout.write(f"Refunds fixed: {fixed_refunds}")
        self.stdout.write(f"Refunds skipped:{skipped_refunds} (ambiguous/no match)")

        if dry_run:
            self.stdout.write("\nDRY RUN complete (no changes saved).")
