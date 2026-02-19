# products/management/commands/backfill_stock_cost_snapshots.py

"""
BACKFILL STOCK MOVEMENT COST SNAPSHOTS (AUDIT SAFE)

Purpose:
- Populate StockMovement.unit_cost_snapshot for legacy movements where it is NULL,
  using the linked StockBatch.unit_cost (single source of truth).

Rules:
- NO guessing: if batch.unit_cost is NULL/invalid, we SKIP and REPORT.
- Idempotent: rerunning is safe.
- Supports --dry-run and --limit for safe iteration.
- Adds reporting to identify which StockBatch rows are missing unit_cost.

Why this matters:
- Makes FIFO/COGS analytics complete.
- Enables deterministic audit reconstruction for sales/refunds.
"""

from __future__ import annotations

from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from products.models import StockMovement


class Command(BaseCommand):
    help = "Backfill StockMovement.unit_cost_snapshot from StockBatch.unit_cost for legacy rows."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would change without saving.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Limit the number of movements to process (0 = no limit).",
        )
        parser.add_argument(
            "--reasons",
            type=str,
            default="",
            help="Comma-separated reasons to include (e.g. SALE,REFUND,RECEIPT). Default: all reasons.",
        )
        parser.add_argument(
            "--report-missing",
            action="store_true",
            help="Report distinct batches that are missing/invalid unit_cost.",
        )
        parser.add_argument(
            "--report-limit",
            type=int,
            default=50,
            help="Max number of missing-cost batches to print in report mode (default 50).",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        dry_run = bool(options.get("dry_run"))
        limit = int(options.get("limit") or 0)
        reasons_raw = (options.get("reasons") or "").strip()
        report_missing = bool(options.get("report_missing"))
        report_limit = int(options.get("report_limit") or 50)

        reasons = []
        if reasons_raw:
            reasons = [r.strip().upper() for r in reasons_raw.split(",") if r.strip()]

        self.stdout.write(
            "Backfilling StockMovement.unit_cost_snapshot from StockBatch.unit_cost..."
        )
        if dry_run:
            self.stdout.write("DRY RUN: no database changes will be saved.\n")

        qs = (
            StockMovement.objects.select_related("batch", "product")
            .filter(unit_cost_snapshot__isnull=True)
            .order_by("created_at")
        )

        if reasons:
            qs = qs.filter(reason__in=reasons)

        if limit > 0:
            qs = qs[:limit]

        updated = 0
        skipped_missing_cost = 0
        skipped_missing_batch = 0

        # Track distinct problematic batches for reporting
        missing_cost_batches = {}  # batch_id -> dict(meta)

        for mv in qs:
            batch = getattr(mv, "batch", None)
            if batch is None:
                skipped_missing_batch += 1
                continue

            batch_cost = getattr(batch, "unit_cost", None)
            ok = True

            if batch_cost is None:
                ok = False
            else:
                try:
                    batch_cost = Decimal(str(batch_cost))
                except Exception:
                    ok = False

            if ok and batch_cost <= Decimal("0.00"):
                ok = False

            if not ok:
                skipped_missing_cost += 1

                if report_missing:
                    bid = str(getattr(batch, "id", ""))
                    if bid and bid not in missing_cost_batches:
                        missing_cost_batches[bid] = {
                            "batch_id": bid,
                            "batch_number": getattr(batch, "batch_number", ""),
                            "product_id": str(getattr(batch, "product_id", "")),
                            "product_name": getattr(
                                getattr(mv, "product", None), "name", ""
                            )
                            or "",
                            "store_id": str(getattr(batch, "store_id", ""))
                            if getattr(batch, "store_id", None)
                            else "",
                            "expiry_date": str(getattr(batch, "expiry_date", "") or ""),
                            "quantity_received": int(
                                getattr(batch, "quantity_received", 0) or 0
                            ),
                            "unit_cost": str(getattr(batch, "unit_cost", "") or ""),
                        }
                continue

            self.stdout.write(
                f"UPDATE movement={mv.id} reason={mv.reason} qty={mv.quantity} "
                f"-> unit_cost_snapshot={batch_cost}"
            )

            if not dry_run:
                mv.unit_cost_snapshot = batch_cost
                mv.save(update_fields=["unit_cost_snapshot"])

            updated += 1

        self.stdout.write("\n--- Summary ---")
        self.stdout.write(f"Updated movements:          {updated}")
        self.stdout.write(f"Skipped (batch missing):    {skipped_missing_batch}")
        self.stdout.write(f"Skipped (cost missing/bad): {skipped_missing_cost}")

        if report_missing:
            self.stdout.write(
                "\n--- Missing/Invalid Batch Costs (distinct batches) ---"
            )
            items = list(missing_cost_batches.values())[: max(report_limit, 0)]
            if not items:
                self.stdout.write("None ✅")
            else:
                for row in items:
                    self.stdout.write(
                        f"- batch_id={row['batch_id']} batch_no={row['batch_number']} "
                        f"product={row['product_name']} product_id={row['product_id']} "
                        f"store_id={row['store_id'] or 'NULL'} expiry={row['expiry_date']} "
                        f"qty_received={row['quantity_received']} unit_cost={row['unit_cost'] or 'NULL'}"
                    )
                if len(missing_cost_batches) > len(items):
                    self.stdout.write(
                        f"...and {len(missing_cost_batches) - len(items)} more. "
                        f"(Increase with --report-limit)"
                    )

        if dry_run:
            self.stdout.write("\nDRY RUN complete (no changes saved).")
