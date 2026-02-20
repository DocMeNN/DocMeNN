# users/management/commands/ensure_superuser.py
"""
PATH: users/management/commands/ensure_superuser.py

Production-safe superuser bootstrap (idempotent).

Env vars:
- AUTO_ADMIN_EMAIL (required)
- AUTO_ADMIN_PASSWORD (required)
- AUTO_ADMIN_USERNAME (optional; defaults to email)
"""

from __future__ import annotations

import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Create or update a production superuser from env vars (idempotent)."

    def handle(self, *args, **options):
        email = (os.getenv("AUTO_ADMIN_EMAIL") or "").strip().lower()
        password = (os.getenv("AUTO_ADMIN_PASSWORD") or "").strip()
        username = (os.getenv("AUTO_ADMIN_USERNAME") or "").strip() or email

        if not email or not password:
            self.stdout.write(self.style.WARNING("ensure_superuser: skipped (missing AUTO_ADMIN_EMAIL/AUTO_ADMIN_PASSWORD)."))
            return

        User = get_user_model()

        # If your user model uses email as USERNAME_FIELD, username may not exist.
        # We'll set what we can safely.
        lookup = {"email": email} if "email" in [f.name for f in User._meta.fields] else {"username": username}

        user = User.objects.filter(**lookup).first()

        created = False
        if not user:
            # Create with the safest fields that exist
            kwargs = {}
            field_names = {f.name for f in User._meta.fields}

            if "email" in field_names:
                kwargs["email"] = email
            if "username" in field_names:
                kwargs["username"] = username

            user = User(**kwargs)
            created = True

        user.is_staff = True
        user.is_superuser = True
        user.is_active = True
        user.set_password(password)
        user.save()

        msg = "created" if created else "updated"
        self.stdout.write(self.style.SUCCESS(f"ensure_superuser: {msg} -> {email}"))