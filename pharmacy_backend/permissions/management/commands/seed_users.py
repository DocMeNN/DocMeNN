# permissions/management/commands/seed_users.py

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from permissions.roles import (
    BUSINESS_PHARMACY,
    BUSINESS_SUPERMARKET,
    BUSINESS_RETAIL,
    BUSINESS_TYPES,
    ROLE_ADMIN,
    ROLE_MANAGER,
    ROLE_CASHIER,
    ROLE_PHARMACIST,
    ROLE_RECEPTION,
)


@dataclass(frozen=True)
class SeedUserSpec:
    label: str
    role: str
    username: str
    email: str


def _model_has_field(model, field_name: str) -> bool:
    try:
        model._meta.get_field(field_name)
        return True
    except Exception:
        return False


def _set_password(user, password: str) -> None:
    # supports both Django default + custom user models
    if hasattr(user, "set_password"):
        user.set_password(password)
    else:
        # extremely unlikely, but safe fallback
        user.password = password


def _upsert_user(
    *,
    User,
    spec: SeedUserSpec,
    password: str,
    is_superuser: bool = False,
    is_staff: bool = True,
) -> tuple[Any, bool]:
    """
    Idempotent user seed:
    - create if missing
    - update role/staff flags if exists
    """
    has_username = _model_has_field(User, "username")
    has_email = _model_has_field(User, "email")

    # Choose lookup key in a predictable way
    if has_email and spec.email:
        lookup = {"email": spec.email}
    elif has_username and spec.username:
        lookup = {"username": spec.username}
    else:
        raise CommandError(
            "Your User model has neither usable email nor username for lookup. "
            "Add an identifier field or adjust seed_users.py to match your User model."
        )

    defaults = {}
    if has_username:
        defaults["username"] = spec.username
    if has_email:
        defaults["email"] = spec.email

    # common fields (safe if they exist)
    if _model_has_field(User, "role"):
        defaults["role"] = spec.role
    if _model_has_field(User, "is_staff"):
        defaults["is_staff"] = bool(is_staff)
    if _model_has_field(User, "is_superuser"):
        defaults["is_superuser"] = bool(is_superuser)

    user, created = User.objects.get_or_create(**lookup, defaults=defaults)

    # Keep idempotent updates aligned
    dirty = False

    if _model_has_field(User, "role") and getattr(user, "role", None) != spec.role:
        user.role = spec.role
        dirty = True

    if _model_has_field(User, "is_staff") and getattr(user, "is_staff", None) != bool(is_staff):
        user.is_staff = bool(is_staff)
        dirty = True

    if _model_has_field(User, "is_superuser") and getattr(user, "is_superuser", None) != bool(is_superuser):
        user.is_superuser = bool(is_superuser)
        dirty = True

    # Set password on create (and optionally on demand)
    if created:
        _set_password(user, password)
        dirty = True

    if dirty:
        user.save()

    return user, created


def _user_specs_for_business(business_type: str) -> list[SeedUserSpec]:
    """
    Business-aware role assignment:
    - pharmacy: admin + manager + pharmacist + cashier + reception
    - supermarket: admin + manager + cashier
    - retail: admin + manager + cashier
    """
    if business_type == BUSINESS_PHARMACY:
        return [
            SeedUserSpec("Admin", ROLE_ADMIN, "admin", "admin@example.com"),
            SeedUserSpec("Manager", ROLE_MANAGER, "manager", "manager@example.com"),
            SeedUserSpec("Pharmacist", ROLE_PHARMACIST, "pharmacist", "pharmacist@example.com"),
            SeedUserSpec("Cashier", ROLE_CASHIER, "cashier", "cashier@example.com"),
            SeedUserSpec("Reception", ROLE_RECEPTION, "reception", "reception@example.com"),
        ]

    if business_type in {BUSINESS_SUPERMARKET, BUSINESS_RETAIL}:
        return [
            SeedUserSpec("Admin", ROLE_ADMIN, "admin", "admin@example.com"),
            SeedUserSpec("Manager", ROLE_MANAGER, "manager", "manager@example.com"),
            SeedUserSpec("Cashier", ROLE_CASHIER, "cashier", "cashier@example.com"),
        ]

    # should never happen due to validation
    return []


class Command(BaseCommand):
    help = "Seed staff users (business-aware: pharmacy vs supermarket vs general retail)."

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
            help="If set, resets password for existing seeded users too.",
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
            raise CommandError("--password must be provided and at least 6 characters.")

        User = get_user_model()
        specs = _user_specs_for_business(business)

        self.stdout.write(f"Seeding users for business='{business}' ...")

        created_count = 0
        updated_count = 0

        for spec in specs:
            is_admin = spec.role == ROLE_ADMIN

            user, created = _upsert_user(
                User=User,
                spec=spec,
                password=password,
                is_superuser=is_admin,
                is_staff=True,
            )

            # Optional: force reset password even if user already existed
            if force_password and not created:
                _set_password(user, password)
                user.save(update_fields=["password"])
                updated_count += 1

            if created:
                created_count += 1
                self.stdout.write(f"✅ created: {spec.label} ({spec.role})")
            else:
                self.stdout.write(f"↩︎ exists:  {spec.label} ({spec.role})")

        self.stdout.write("\n--- Summary ---")
        self.stdout.write(f"Created users: {created_count}")
        if force_password:
            self.stdout.write(f"Passwords reset: {updated_count}")
        self.stdout.write("\nLogin usernames/emails depend on your User model fields.")
        self.stdout.write("Default seeded accounts use: admin / manager / cashier (+ pharmacist/reception in pharmacy).")
