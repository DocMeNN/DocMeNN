# accounting/management/commands/reset_test_data.py

from __future__ import annotations

from django.apps import apps
from django.core.management.base import BaseCommand
from django.db import connection, transaction


def _model_table(app_label: str, model_name: str) -> str | None:
    """
    Return DB table for a model if it exists, else None.
    This keeps the command resilient across refactors.
    """
    try:
        model = apps.get_model(app_label, model_name)
        return model._meta.db_table
    except Exception:
        return None


def _run_sql(sql: str):
    with connection.cursor() as cursor:
        cursor.execute(sql)


def _wipe_tables(tables: list[str]):
    """
    DB-vendor-safe wipe.

    - Postgres: TRUNCATE ... RESTART IDENTITY CASCADE (fast, clean)
    - SQLite: disable FK checks; DELETE FROM each table
    - MySQL: disable FK checks; TRUNCATE (or DELETE) each table
    """
    tables = [t for t in tables if t]  # remove None/empty
    # de-dupe while preserving order
    seen = set()
    tables = [t for t in tables if not (t in seen or seen.add(t))]

    if not tables:
        return

    vendor = connection.vendor

    if vendor == "postgresql":
        quoted = ", ".join([f'"{t}"' for t in tables])
        _run_sql(f"TRUNCATE TABLE {quoted} RESTART IDENTITY CASCADE;")
        return

    if vendor == "sqlite":
        _run_sql("PRAGMA foreign_keys = OFF;")
        try:
            for t in tables:
                _run_sql(f'DELETE FROM "{t}";')
        finally:
            _run_sql("PRAGMA foreign_keys = ON;")
        return

    if vendor == "mysql":
        _run_sql("SET FOREIGN_KEY_CHECKS=0;")
        try:
            for t in tables:
                # TRUNCATE is faster, but some FK setups complain; DELETE is safest.
                _run_sql(f"DELETE FROM `{t}`;")
        finally:
            _run_sql("SET FOREIGN_KEY_CHECKS=1;")
        return

    # Fallback: try delete each table
    for t in tables:
        try:
            _run_sql(f'DELETE FROM "{t}";')
        except Exception:
            _run_sql(f"DELETE FROM {t};")


class Command(BaseCommand):
    help = (
        "Hard reset for TESTING: clears accounting postings + sales + inventory movements "
        "so reports return to zero. Use with caution."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--i-am-sure",
            action="store_true",
            help="Required safety flag. Without this, the command will not run.",
        )
        parser.add_argument(
            "--include-products",
            action="store_true",
            help="Also clears inventory batches/movements (recommended for clean profit/COGS tests).",
        )
        parser.add_argument(
            "--include-accounts",
            action="store_true",
            help="Also clears ChartOfAccounts + Accounts (NOT usually needed).",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if not options.get("i_am_sure"):
            self.stdout.write(self.style.ERROR("Refusing to run without --i-am-sure"))
            self.stdout.write(
                "Example: python manage.py reset_test_data --i-am-sure --include-products"
            )
            return

        include_products = bool(options.get("include_products"))
        include_accounts = bool(options.get("include_accounts"))

        self.stdout.write(self.style.WARNING("RESETTING TEST DATA..."))

        # ----------------------------
        # Choose tables to wipe
        # ----------------------------
        tables: list[str] = []

        # --- SALES (so POS reports + refund state clears) ---
        # NOTE: use table wipe (not .delete()) because some models enforce immutability.
        tables += [
            _model_table("sales", "SaleItem"),
            _model_table("sales", "SaleRefundAudit"),
            _model_table("sales", "Sale"),
        ]

        # --- POS / CART (if you have it) ---
        tables += [
            _model_table("pos", "CartItem"),
            _model_table("pos", "Cart"),
        ]

        # --- ACCOUNTING (journal/ledger truth that powers Trial Balance / P&L / Balance Sheet) ---
        # Adjust names if yours differ; missing ones are skipped safely.
        tables += [
            _model_table("accounting", "LedgerEntry"),
            _model_table("accounting", "JournalLine"),
            _model_table("accounting", "JournalEntry"),
        ]

        # --- OPTIONAL: PRODUCTS / INVENTORY (needed if you want clean COGS + stock history) ---
        if include_products:
            tables += [
                _model_table("products", "StockMovement"),
                _model_table("products", "StockBatch"),
            ]

        # --- OPTIONAL: Accounts/Charts (rarely needed; wipes setup) ---
        if include_accounts:
            tables += [
                _model_table("accounting", "Account"),
                _model_table("accounting", "ChartOfAccounts"),
            ]

        # ----------------------------
        # Execute wipe
        # ----------------------------
        # For Postgres, CASCADE handles ordering. For others, we already list children first.
        _wipe_tables(tables)

        # Clear chart resolver cache if present
        try:
            from accounting.services.account_resolver import clear_active_chart_cache

            clear_active_chart_cache()
        except Exception:
            pass

        self.stdout.write(self.style.SUCCESS("Done. Test data cleared."))

        # Helpful guidance
        self.stdout.write("\nNext steps:")
        self.stdout.write("1) Restart backend server (optional but good).")
        self.stdout.write("2) Hard refresh frontend (Ctrl+Shift+R).")
        self.stdout.write(
            "3) If you use React Query, consider clearing cache / reload app."
        )
