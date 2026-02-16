# accounting/management/commands/sync_pos_to_ledger.py

from __future__ import annotations

from datetime import datetime

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from accounting.models.journal import JournalEntry
from accounting.services.posting import post_sale_to_ledger, post_refund_to_ledger
from sales.models.sale import Sale
from sales.models.refund_audit import SaleRefundAudit


def _parse_date(s: str | None):
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


def _bounds(date_from, date_to):
    tz = timezone.get_current_timezone()

    if date_from and not date_to:
        date_to = date_from
    if date_to and not date_from:
        date_from = date_to
    if not date_from and not date_to:
        return None, None

    start = timezone.make_aware(datetime.combine(date_from, datetime.min.time()), tz)
    end = timezone.make_aware(datetime.combine(date_to, datetime.min.time()), tz) + timezone.timedelta(days=1)
    return start, end


def _sale_desc_prefix(inv_or_id: str) -> str:
    return f"POS Sale {inv_or_id}"


def _refund_desc_prefix(inv_or_id: str) -> str:
    return f"POS Refund {inv_or_id}"


class Command(BaseCommand):
    help = "Create missing POS_SALE / POS_REFUND journal entries for existing historical sales/refunds."

    def add_arguments(self, parser):
        parser.add_argument("--from", dest="date_from", help="Start date YYYY-MM-DD (optional)")
        parser.add_argument("--to", dest="date_to", help="End date YYYY-MM-DD (optional)")
        parser.add_argument("--dry-run", action="store_true", help="Show actions without writing to DB")
        parser.add_argument(
            "--force",
            action="store_true",
            help="Post even if a journal entry exists with matching invoice_no in description (NOT recommended).",
        )

    def handle(self, *args, **options):
        date_from = _parse_date(options.get("date_from"))
        date_to = _parse_date(options.get("date_to"))
        dry_run = bool(options.get("dry_run"))
        force = bool(options.get("force"))

        if options.get("date_from") and not date_from:
            self.stderr.write(self.style.ERROR("Invalid --from date. Use YYYY-MM-DD"))
            raise SystemExit(1)
        if options.get("date_to") and not date_to:
            self.stderr.write(self.style.ERROR("Invalid --to date. Use YYYY-MM-DD"))
            raise SystemExit(1)

        start, end = _bounds(date_from, date_to)

        # -----------------------------
        # Base querysets
        # -----------------------------
        sales_qs = Sale.objects.filter(status=Sale.STATUS_COMPLETED)

        refunds_qs = (
            SaleRefundAudit.objects
            .select_related("sale")
        )

        if start and end:
            sales_qs = sales_qs.filter(completed_at__gte=start, completed_at__lt=end)
            refunds_qs = refunds_qs.filter(refunded_at__gte=start, refunded_at__lt=end)

        # -----------------------------
        # DEBUG COUNTS (THIS IS THE KEY)
        # -----------------------------
        total_sales = sales_qs.count()
        total_refunds = refunds_qs.count()

        self.stdout.write(self.style.MIGRATE_HEADING("Sync POS → Ledger"))
        if start and end:
            self.stdout.write(f"Window: {start.isoformat()} → {end.isoformat()}")
        else:
            self.stdout.write("Window: ALL TIME")

        self.stdout.write(f"DEBUG: Completed sales found: {total_sales}")
        self.stdout.write(f"DEBUG: Refund audits found:   {total_refunds}")

        if total_sales == 0:
            distinct_statuses = list(Sale.objects.values_list("status", flat=True).distinct())
            self.stdout.write(self.style.WARNING(f"DEBUG: Distinct Sale.status values in DB: {distinct_statuses}"))
            self.stdout.write(self.style.WARNING(f"DEBUG: Sale.STATUS_COMPLETED constant: {Sale.STATUS_COMPLETED!r}"))

        if dry_run:
            self.stdout.write("DRY RUN: no database changes will be saved.\n")

        posted_sales = 0
        skipped_sales = 0
        failed_sales = 0

        posted_refunds = 0
        skipped_refunds = 0
        failed_refunds = 0

        errors: list[str] = []

        # -----------------------------
        # SALES (load fields used by posting)
        # -----------------------------
        sales_qs = sales_qs.only(
            "id",
            "invoice_no",
            "completed_at",
            "total_amount",
            "subtotal_amount",
            "tax_amount",
            "discount_amount",
            "payment_method",
        )

        for sale in sales_qs.iterator():
            ref = f"POS_SALE:{sale.id}"

            if JournalEntry.objects.filter(reference=ref).exists():
                # DEBUG (silent skip reason)
                continue

            inv = (getattr(sale, "invoice_no", None) or "").strip()
            if inv and not force:
                expected_prefix = _sale_desc_prefix(inv)
                if JournalEntry.objects.filter(description__startswith=expected_prefix).exists():
                    skipped_sales += 1
                    continue

            self.stdout.write(f"POST SALE  {inv or sale.id} -> {ref}")

            if dry_run:
                posted_sales += 1
                continue

            try:
                with transaction.atomic():
                    post_sale_to_ledger(sale=sale)
                posted_sales += 1
            except Exception as exc:
                failed_sales += 1
                errors.append(f"SALE {inv or sale.id}: {exc}")

        # -----------------------------
        # REFUNDS (load fields used by posting)
        # -----------------------------
        refunds_qs = refunds_qs.only(
            "id",
            "refunded_at",
            "original_total_amount",
            "sale__id",
            "sale__invoice_no",
            "sale__total_amount",
            "sale__subtotal_amount",
            "sale__tax_amount",
            "sale__discount_amount",
            "sale__payment_method",
        )

        for audit in refunds_qs.iterator():
            ref = f"POS_REFUND:{audit.id}"

            if JournalEntry.objects.filter(reference=ref).exists():
                continue

            inv = (getattr(audit.sale, "invoice_no", None) or "").strip()

            if inv and not force:
                expected_prefix = _refund_desc_prefix(inv)
                if JournalEntry.objects.filter(description__startswith=expected_prefix).exists():
                    skipped_refunds += 1
                    continue

            self.stdout.write(f"POST REFUND {inv or audit.id} -> {ref}")

            if dry_run:
                posted_refunds += 1
                continue

            try:
                with transaction.atomic():
                    post_refund_to_ledger(sale=audit.sale, refund_audit=audit)
                posted_refunds += 1
            except Exception as exc:
                failed_refunds += 1
                errors.append(f"REFUND {inv or audit.id}: {exc}")

        self.stdout.write("\n--- Summary ---")
        self.stdout.write(f"Sales posted:    {posted_sales}")
        self.stdout.write(f"Sales skipped:   {skipped_sales} (existing POS Sale by invoice prefix)")
        self.stdout.write(f"Sales failed:    {failed_sales}")
        self.stdout.write(f"Refunds posted:  {posted_refunds}")
        self.stdout.write(f"Refunds skipped: {skipped_refunds} (existing POS Refund by invoice prefix)")
        self.stdout.write(f"Refunds failed:  {failed_refunds}")

        if errors:
            self.stdout.write("\n--- Errors ---")
            for e in errors[:50]:
                self.stdout.write(f"- {e}")
            if len(errors) > 50:
                self.stdout.write(f"... ({len(errors) - 50} more)")

            if not dry_run:
                raise SystemExit(2)
