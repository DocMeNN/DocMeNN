# accounting/management/commands/seed_supermarket_chart.py

from django.core.management.base import BaseCommand
from django.db import transaction

from accounting.models.account import Account
from accounting.models.chart import ChartOfAccounts


def _activate_only_this_chart(chart: ChartOfAccounts) -> None:
    ChartOfAccounts.objects.exclude(id=chart.id).filter(is_active=True).update(
        is_active=False
    )
    if not chart.is_active:
        chart.is_active = True
        chart.save(update_fields=["is_active"])


class Command(BaseCommand):
    help = "Seed Chart of Accounts + required accounts for Supermarket business"

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write("Seeding Supermarket Chart of Accounts...")

        chart, created = ChartOfAccounts.objects.get_or_create(
            name="Supermarket",
            defaults={
                "industry": "RETAIL",
                "code": "supermarket_standard",
                "business_type": ChartOfAccounts.BUSINESS_SUPERMARKET,
                "is_active": True,
            },
        )

        changed = False
        if chart.industry != "RETAIL":
            chart.industry = "RETAIL"
            changed = True
        if not chart.code:
            chart.code = "supermarket_standard"
            changed = True
        if not chart.business_type:
            chart.business_type = ChartOfAccounts.BUSINESS_SUPERMARKET
            changed = True
        if changed:
            chart.save()

        _activate_only_this_chart(chart)

        accounts = [
            ("1000", "Cash on Hand", Account.ASSET),
            ("1010", "Bank Account", Account.ASSET),
            ("1100", "Accounts Receivable", Account.ASSET),
            ("1200", "Inventory", Account.ASSET),
            ("2000", "Accounts Payable", Account.LIABILITY),
            ("2100", "VAT Payable", Account.LIABILITY),
            ("3000", "Owner Capital", Account.EQUITY),
            ("3100", "Retained Earnings", Account.EQUITY),
            ("4000", "Sales Revenue", Account.REVENUE),
            ("4050", "Sales Discounts", Account.REVENUE),
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
                f"✔ Supermarket chart seeded ({created_count} new accounts, {updated_count} updated)."
            )
        )
