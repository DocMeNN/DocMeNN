# accounting/management/commands/seed_users.py

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.db import transaction


User = get_user_model()


DEFAULT_PASSWORD = "Pass1234!"  # dev only; change for production


class Command(BaseCommand):
    help = "Seed staff users for a selected business type (business-aware roles)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--business",
            choices=["pharmacy", "supermarket", "retail"],
            default="supermarket",
            help="Which business type to seed users for.",
        )
        parser.add_argument(
            "--password",
            default=DEFAULT_PASSWORD,
            help="Password for all seeded users (dev only).",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        business = options["business"]
        password = options["password"]

        self.stdout.write(f"Seeding users for business={business} ...")

        # Roles must match users/models/user.py ROLE_CHOICES
        # - pharmacist only exists/used for pharmacy
        role_sets = {
            "pharmacy": [
                ("admin", "admin_pharmacy@example.com", "Pharmacy", "Admin"),
                ("pharmacist", "pharmacist@example.com", "Pharmacy", "Pharmacist"),
                ("cashier", "cashier_pharmacy@example.com", "Pharmacy", "Cashier"),
                ("reception", "reception_pharmacy@example.com", "Pharmacy", "Reception"),
            ],
            "supermarket": [
                ("admin", "admin_supermarket@example.com", "Supermarket", "Admin"),
                ("cashier", "cashier_supermarket@example.com", "Supermarket", "Cashier"),
                ("reception", "reception_supermarket@example.com", "Supermarket", "Reception"),
            ],
            "retail": [
                ("admin", "admin_retail@example.com", "Retail", "Admin"),
                ("cashier", "cashier_retail@example.com", "Retail", "Cashier"),
                ("reception", "reception_retail@example.com", "Retail", "Reception"),
            ],
        }

        users_to_seed = role_sets[business]

        created = 0
        updated = 0

        for role, email, first_name, last_name in users_to_seed:
            user = User.objects.filter(email=email).first()
            if user is None:
                # Staff users: is_staff True
                user = User.objects.create_user(
                    email=email,
                    password=password,
                    role=role,
                    first_name=first_name,
                    last_name=last_name,
                    is_staff=True,
                    is_active=True,
                )
                created += 1
            else:
                # Corrective re-run: ensure role + staff flag
                changed = False
                if user.role != role:
                    user.role = role
                    changed = True
                if not user.is_staff:
                    user.is_staff = True
                    changed = True
                if not user.is_active:
                    user.is_active = True
                    changed = True

                if changed:
                    user.save(update_fields=["role", "is_staff", "is_active"])
                    updated += 1

                # Optionally reset password every run (dev convenience)
                user.set_password(password)
                user.save(update_fields=["password"])

        self.stdout.write(self.style.SUCCESS(
            f"✔ Users seeded for {business}: {created} created, {updated} updated. "
            f"Password set to: {password}"
        ))

        self.stdout.write("Next: login with one of the seeded emails in admin / swagger.")
