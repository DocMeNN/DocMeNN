# accounting/management/commands/seed_pharmacy_chart.py

from django.core.management.base import BaseCommand
from django.db import transaction

from accounting.models.account import Account
from accounting.models.chart import ChartOfAccounts

PHARMACY_CODE = "pharmacy_standard"
PHARMACY_NAME = "Pharmacy Standard Chart"
PHARMACY_INDUSTRY = "Pharmaceuticals"


def _activate_only_this_chart(chart: ChartOfAccounts) -> None:
    ChartOfAccounts.objects.exclude(id=chart.id).filter(is_active=True).update(
        is_active=False
    )
    if not chart.is_active:
        chart.is_active = True
        chart.save(update_fields=["is_active"])


class Command(BaseCommand):
    help = "Seed default Chart of Accounts + required accounts for a Pharmacy business"

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write("Seeding Pharmacy Chart of Accounts...")

        # ------------------------------------------------------------
        # ✅ IMPORTANT: Resolve by STABLE code first (tenant-safe key)
        # ------------------------------------------------------------
        qs = ChartOfAccounts.objects.filter(code=PHARMACY_CODE).order_by("id")
        if qs.exists():
            chart = qs.first()
            created = False
        else:
            # Fallback for legacy DBs: find by name if code isn't set yet
            chart = (
                ChartOfAccounts.objects.filter(name__iexact=PHARMACY_NAME).first()
                or ChartOfAccounts.objects.filter(name__iexact="Pharmacy").first()
            )
            created = chart is None

        if created:
            chart = ChartOfAccounts.objects.create(
                name=PHARMACY_NAME,
                industry=PHARMACY_INDUSTRY,
                code=PHARMACY_CODE,
                business_type=ChartOfAccounts.BUSINESS_PHARMACY,
                is_active=True,
            )
            self.stdout.write("Created Pharmacy chart")
        else:
            # Backfill / correct existing row
            changed = False

            if (chart.name or "").strip() != PHARMACY_NAME:
                chart.name = PHARMACY_NAME
                changed = True

            if (getattr(chart, "industry", "") or "").strip() != PHARMACY_INDUSTRY:
                chart.industry = PHARMACY_INDUSTRY
                changed = True

            if not (getattr(chart, "code", None) or "").strip():
                chart.code = PHARMACY_CODE
                changed = True

            if not (getattr(chart, "business_type", None) or "").strip():
                chart.business_type = ChartOfAccounts.BUSINESS_PHARMACY
                changed = True

            if changed:
                chart.save()

            self.stdout.write("Pharmacy chart already exists (updated if needed)")

        _activate_only_this_chart(chart)

        accounts = [
            # ASSETS
            ("1000", "Cash on Hand", Account.ASSET),
            ("1010", "Bank Account", Account.ASSET),
            ("1100", "Inventory", Account.ASSET),
            ("1200", "Accounts Receivable", Account.ASSET),
            # LIABILITIES
            ("2000", "Accounts Payable", Account.LIABILITY),
            ("2100", "VAT Payable", Account.LIABILITY),
            # EQUITY
            ("3000", "Owner Capital", Account.EQUITY),
            ("3100", "Retained Earnings", Account.EQUITY),
            # REVENUE
            ("4000", "Sales Revenue", Account.REVENUE),
            ("4050", "Sales Discounts", Account.REVENUE),  # contra-revenue
            # EXPENSES
            ("5000", "Cost of Goods Sold", Account.EXPENSE),
            ("6000", "Operating Expenses", Account.EXPENSE),
        ]

        created_count = 0
        updated_count = 0

        for code, name, account_type in accounts:
            acc, acc_created = Account.objects.get_or_create(
                chart=chart,
                code=code,
                defaults={
                    "name": name,
                    "account_type": account_type,
                    "is_active": True,
                },
            )

            if acc_created:
                created_count += 1
                continue

            needs_update = False
            if acc.name != name:
                acc.name = name
                needs_update = True
            if acc.account_type != account_type:
                acc.account_type = account_type
                needs_update = True
            if not acc.is_active:
                acc.is_active = True
                needs_update = True

            if needs_update:
                acc.save(update_fields=["name", "account_type", "is_active"])
                updated_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"✔ Pharmacy chart seeded ({created_count} new accounts, {updated_count} updated)."
            )
        )