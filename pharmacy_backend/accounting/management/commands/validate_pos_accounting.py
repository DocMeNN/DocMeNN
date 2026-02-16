# accounting/management/commands/validate_pos_accounting.py

from __future__ import annotations

from datetime import datetime

from django.core.management.base import BaseCommand
from django.db.models import Sum
from django.utils import timezone

from accounting.models.journal import JournalEntry
from accounting.models.ledger import LedgerEntry
from sales.models.sale import Sale
from sales.models.refund_audit import SaleRefundAudit


def _parse_date(s: str | None):
    """
    Parse YYYY-MM-DD into a date, or None.
    """
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


def _bounds(date_from, date_to):
    """
    Produce timezone-aware [start, end) bounds.
    If only one side provided, treat as single-day.
    """
    tz = timezone.get_current_timezone()

    if date_from and not date_to:
        date_to = date_from

    if not date_from and date_to:
        date_from = date_to

    if not date_from and not date_to:
        return None, None

    start = timezone.make_aware(datetime.combine(date_from, datetime.min.time()), tz)
    end = timezone.make_aware(datetime.combine(date_to, datetime.min.time()), tz) + timezone.timedelta(days=1)
    return start, end


class Command(BaseCommand):
    help = "Validate POS → Accounting integrity (sales/refunds references + ledger balance)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--from",
            dest="date_from",
            help="Start date YYYY-MM-DD (optional)",
        )
        parser.add_argument(
            "--to",
            dest="date_to",
            help="End date YYYY-MM-DD (optional)",
        )
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Fail (non-zero exit) if any error is found.",
        )

    def handle(self, *args, **options):
        date_from = _parse_date(options.get("date_from"))
        date_to = _parse_date(options.get("date_to"))
        strict = bool(options.get("strict"))

        if options.get("date_from") and not date_from:
            self.stderr.write(self.style.ERROR("Invalid --from date. Use YYYY-MM-DD"))
            return self._exit(strict)

        if options.get("date_to") and not date_to:
            self.stderr.write(self.style.ERROR("Invalid --to date. Use YYYY-MM-DD"))
            return self._exit(strict)

        start, end = _bounds(date_from, date_to)

        # -----------------------------
        # Filter sales/refunds window
        # -----------------------------
        sales_qs = Sale.objects.filter(status=Sale.STATUS_COMPLETED)
        refunds_qs = SaleRefundAudit.objects.all()

        if start and end:
            sales_qs = sales_qs.filter(completed_at__gte=start, completed_at__lt=end)
            refunds_qs = refunds_qs.filter(refunded_at__gte=start, refunded_at__lt=end)

        total_sales = sales_qs.count()
        total_refunds = refunds_qs.count()

        self.stdout.write(self.style.MIGRATE_HEADING("POS → Accounting Validation"))
        if start and end:
            self.stdout.write(f"Window: {start.isoformat()}  →  {end.isoformat()}")
        else:
            self.stdout.write("Window: ALL TIME")

        self.stdout.write(f"Completed sales in window: {total_sales}")
        self.stdout.write(f"Refund audits in window:   {total_refunds}")
        self.stdout.write("")

        errors = 0

        # -----------------------------
        # 1) Sales → Journal reference
        # -----------------------------
        missing_sales_refs = []
        duplicate_sales_refs = []

        for sale_id in sales_qs.values_list("id", flat=True):
            ref = f"POS_SALE:{sale_id}"
            count = JournalEntry.objects.filter(reference=ref).count()
            if count == 0:
                missing_sales_refs.append(str(sale_id))
            elif count > 1:
                duplicate_sales_refs.append((str(sale_id), count))

        if missing_sales_refs:
            errors += len(missing_sales_refs)
            self.stderr.write(self.style.ERROR(f"[FAIL] Missing POS_SALE journal entries: {len(missing_sales_refs)}"))
            self.stderr.write("  Example IDs: " + ", ".join(missing_sales_refs[:10]))

        if duplicate_sales_refs:
            errors += len(duplicate_sales_refs)
            self.stderr.write(self.style.ERROR(f"[FAIL] Duplicate POS_SALE journal entries: {len(duplicate_sales_refs)}"))
            for sid, cnt in duplicate_sales_refs[:10]:
                self.stderr.write(f"  sale_id={sid} count={cnt}")

        if not missing_sales_refs and not duplicate_sales_refs:
            self.stdout.write(self.style.SUCCESS("[OK] Sales references look good (POS_SALE:<sale.id>)"))

        # -----------------------------
        # 2) Refunds → Journal reference
        # -----------------------------
        missing_refund_refs = []
        duplicate_refund_refs = []

        for audit_id in refunds_qs.values_list("id", flat=True):
            ref = f"POS_REFUND:{audit_id}"
            count = JournalEntry.objects.filter(reference=ref).count()
            if count == 0:
                missing_refund_refs.append(str(audit_id))
            elif count > 1:
                duplicate_refund_refs.append((str(audit_id), count))

        if missing_refund_refs:
            errors += len(missing_refund_refs)
            self.stderr.write(self.style.ERROR(f"[FAIL] Missing POS_REFUND journal entries: {len(missing_refund_refs)}"))
            self.stderr.write("  Example IDs: " + ", ".join(missing_refund_refs[:10]))

        if duplicate_refund_refs:
            errors += len(duplicate_refund_refs)
            self.stderr.write(self.style.ERROR(f"[FAIL] Duplicate POS_REFUND journal entries: {len(duplicate_refund_refs)}"))
            for rid, cnt in duplicate_refund_refs[:10]:
                self.stderr.write(f"  refund_audit_id={rid} count={cnt}")

        if not missing_refund_refs and not duplicate_refund_refs:
            self.stdout.write(self.style.SUCCESS("[OK] Refund references look good (POS_REFUND:<audit.id>)"))

        # -----------------------------
        # 3) Ledger global balance check
        # -----------------------------
        ledger_qs = LedgerEntry.objects.all()
        if start and end:
            # Ledger entries time is typically journal_entry.posted_at
            ledger_qs = ledger_qs.filter(journal_entry__posted_at__gte=start, journal_entry__posted_at__lt=end)

        debits = (
            ledger_qs.filter(entry_type=LedgerEntry.DEBIT)
            .aggregate(total=Sum("amount"))
            .get("total")
            or 0
        )
        credits = (
            ledger_qs.filter(entry_type=LedgerEntry.CREDIT)
            .aggregate(total=Sum("amount"))
            .get("total")
            or 0
        )

        if debits != credits:
            errors += 1
            self.stderr.write(self.style.ERROR(f"[FAIL] Ledger not balanced: debits={debits} credits={credits}"))
        else:
            self.stdout.write(self.style.SUCCESS(f"[OK] Ledger balanced: debits={debits} credits={credits}"))

        self.stdout.write("")
        if errors == 0:
            self.stdout.write(self.style.SUCCESS("✅ VALIDATION PASSED (Phase 1.3 proof check)"))
        else:
            self.stderr.write(self.style.ERROR(f"❌ VALIDATION FOUND ISSUES: {errors} problem(s)"))

        return self._exit(strict and errors > 0)

    def _exit(self, fail: bool):
        if fail:
            raise SystemExit(1)
        return None
