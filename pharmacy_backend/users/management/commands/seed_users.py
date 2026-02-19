# users/management/commands/seed_users.py

from __future__ import annotations

from dataclasses import dataclass

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from permissions.roles import (
    BUSINESS_PHARMACY,
    BUSINESS_RETAIL,
    BUSINESS_SUPERMARKET,
    BUSINESS_TYPES,
    ROLE_ADMIN,
    ROLE_CASHIER,
    ROLE_MANAGER,
    ROLE_PHARMACIST,
    ROLE_RECEPTION,
)


@dataclass(frozen=True)
class SeedUserSpec:
    label: str
    role: str
    email: str
    first_name: str = ""
    last_name: str = ""


def _has_field(User, field_name: str) -> bool:
    try:
        User._meta.get_field(field_name)
        return True
    except Exception:
        return False


def _set_password(user, password: str) -> None:
    user.set_password(password)


def _user_specs_for_business(business_type: str) -> list[SeedUserSpec]:
    """
    Business-aware role assignment:
    - pharmacy: admin + manager + pharmacist + cashier + reception
    - supermarket: admin + manager + cashier
    - retail: admin + manager + cashier
    """
    if business_type == BUSINESS_PHARMACY:
        return [
            SeedUserSpec("Admin", ROLE_ADMIN, "admin@example.com", "System", "Admin"),
            SeedUserSpec(
                "Manager", ROLE_MANAGER, "manager@example.com", "Store", "Manager"
            ),
            SeedUserSpec(
                "Pharmacist",
                ROLE_PHARMACIST,
                "pharmacist@example.com",
                "Lead",
                "Pharmacist",
            ),
            SeedUserSpec(
                "Cashier", ROLE_CASHIER, "cashier@example.com", "Front", "Desk"
            ),
            SeedUserSpec(
                "Reception",
                ROLE_RECEPTION,
                "reception@example.com",
                "Reception",
                "Staff",
            ),
        ]

    if business_type in {BUSINESS_SUPERMARKET, BUSINESS_RETAIL}:
        return [
            SeedUserSpec("Admin", ROLE_ADMIN, "admin@example.com", "System", "Admin"),
            SeedUserSpec(
                "Manager", ROLE_MANAGER, "manager@example.com", "Store", "Manager"
            ),
            SeedUserSpec(
                "Cashier", ROLE_CASHIER, "cashier@example.com", "Front", "Desk"
            ),
        ]

    return []


class Command(BaseCommand):
    help = "Seed staff users (business-aware)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--business",
            type=str,
            default=BUSINESS_SUPERMARKET,
            help="Business type: pharmacy | supermarket | retail (default: supermarket)",
        )
        parser.add_argument(
            "--password",
            type=str,
            default="Pass1234!",
            help="Password for seeded users (default: Pass1234!)",
        )
        parser.add_argument(
            "--force-password",
            action="store_true",
            help="Reset password for existing seeded users too.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        business = (options.get("business") or "").strip().lower()
        password = options.get("password") or ""
        force_password = bool(options.get("force_password"))

        if business not in BUSINESS_TYPES:
            raise CommandError(
                f"Invalid --business '{business}'. Must be one of: {sorted(BUSINESS_TYPES)}"
            )

        if not password or len(password) < 6:
            raise CommandError("--password must be at least 6 characters.")

        User = get_user_model()

        # Sanity: required fields
        if not _has_field(User, "email"):
            raise CommandError(
                "Your User model must have an 'email' field for this seed command."
            )

        specs = _user_specs_for_business(business)

        self.stdout.write(f"Seeding users for business='{business}' ...")

        created_count = 0
        updated_count = 0
        pw_reset_count = 0

        for spec in specs:
            is_admin = spec.role == ROLE_ADMIN

            defaults = {
                "role": spec.role,
                "is_staff": True,
                "is_superuser": bool(is_admin),
                "is_active": True,
            }

            if _has_field(User, "first_name"):
                defaults["first_name"] = spec.first_name
            if _has_field(User, "last_name"):
                defaults["last_name"] = spec.last_name

            user, created = User.objects.get_or_create(
                email=spec.email, defaults=defaults
            )

            dirty = False

            # Keep aligned with desired seed spec
            if getattr(user, "role", None) != spec.role:
                user.role = spec.role
                dirty = True

            if getattr(user, "is_staff", None) is not True:
                user.is_staff = True
                dirty = True

            if getattr(user, "is_superuser", None) != bool(is_admin):
                user.is_superuser = bool(is_admin)
                dirty = True

            if getattr(user, "is_active", None) is not True:
                user.is_active = True
                dirty = True

            if (
                _has_field(User, "first_name")
                and spec.first_name
                and getattr(user, "first_name", "") != spec.first_name
            ):
                user.first_name = spec.first_name
                dirty = True

            if (
                _has_field(User, "last_name")
                and spec.last_name
                and getattr(user, "last_name", "") != spec.last_name
            ):
                user.last_name = spec.last_name
                dirty = True

            if created:
                _set_password(user, password)
                dirty = True

            if force_password and not created:
                _set_password(user, password)
                dirty = True
                pw_reset_count += 1

            if dirty:
                user.save()
                if not created:
                    updated_count += 1

            if created:
                created_count += 1
                self.stdout.write(
                    f"✅ created: {spec.label} ({spec.role}) -> {spec.email}"
                )
            else:
                self.stdout.write(
                    f"↩︎ exists:  {spec.label} ({spec.role}) -> {spec.email}"
                )

        self.stdout.write("\n--- Summary ---")
        self.stdout.write(f"Created: {created_count}")
        self.stdout.write(f"Updated: {updated_count}")
        if force_password:
            self.stdout.write(f"Passwords reset: {pw_reset_count}")

        self.stdout.write("\nRun example:")
        self.stdout.write(
            "  python manage.py seed_users --business supermarket --password Pass1234!"
        )
