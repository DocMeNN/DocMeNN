# pharmacy_backend/users/management/commands/ensure_superuser.py

"""
PATH: users/management/commands/ensure_superuser.py

Production-safe superuser bootstrap.

- Reads AUTO_ADMIN_EMAIL + AUTO_ADMIN_PASSWORD from env.
- Idempotent: creates superuser if missing; updates password if user exists.
- Safe for Render free plan (no shell).
- Logs minimal info; does NOT print the password.
"""

from __future__ import annotations

import os

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.db import transaction


class Command(BaseCommand):
    help = "Create/update an initial superuser from env vars (idempotent)."

    def handle(self, *args, **options):
        email = (os.environ.get("AUTO_ADMIN_EMAIL") or "").strip()
        password = (os.environ.get("AUTO_ADMIN_PASSWORD") or "").strip()

        if not email or not password:
            self.stdout.write(self.style.WARNING("AUTO_ADMIN_* env vars not set. Skipping."))
            return

        User = get_user_model()

        # Prefer email if the model has it, otherwise fall back to username.
        email_field_exists = any(f.name == "email" for f in User._meta.fields)
        username_field = getattr(User, "USERNAME_FIELD", "username")

        lookup = {}
        if email_field_exists:
            lookup["email"] = email
        else:
            lookup[username_field] = email  # fallback

        with transaction.atomic():
            user = User.objects.filter(**lookup).first()

            if user:
                # Ensure it is staff + superuser and reset password to the env password.
                user.is_active = True
                user.is_staff = True
                user.is_superuser = True
                user.set_password(password)

                # If user has email field but it's blank and our lookup didn't use it, set it
                if email_field_exists and not getattr(user, "email", ""):
                    user.email = email

                user.save()
                self.stdout.write(self.style.SUCCESS(f"Superuser ensured: {email} (updated)"))
                return

            # Create new superuser
            create_kwargs = {}
            if email_field_exists:
                create_kwargs["email"] = email

            # Some custom user models require username even if USERNAME_FIELD=email.
            # If username is required and different from email field, set it.
            if username_field and username_field != "email":
                # only set if the field exists
                if any(f.name == username_field for f in User._meta.fields):
                    create_kwargs[username_field] = email

            try:
                user = User.objects.create_superuser(**create_kwargs, password=password)
            except TypeError:
                # Some custom create_superuser signatures require positional args.
                # Fallback: create user manually.
                user = User(**create_kwargs)
                user.is_active = True
                user.is_staff = True
                user.is_superuser = True
                user.set_password(password)
                user.save()

            self.stdout.write(self.style.SUCCESS(f"Superuser ensured: {email} (created)"))
