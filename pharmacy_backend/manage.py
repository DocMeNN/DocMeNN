"""
PATH: manage.py

Django management entrypoint.

Key safeguard:
- If DJANGO_SETTINGS_MODULE is unset OR incorrectly set to the settings *package*
  ("backend.settings"), we force it to a concrete module ("backend.settings.dev").

Why:
- "backend.settings" is a package; your __init__.py intentionally loads nothing.
  That leads to missing INSTALLED_APPS in CI/test runs, breaking model imports.

Production:
- Production must set DJANGO_SETTINGS_MODULE=backend.settings.prod explicitly.
  We respect that.

Temporary production recovery hook:
- If RUN_CREATE_SUPERUSER=True is set in environment variables,
  a superuser will be created automatically (if not existing).
- REMOVE this after regaining admin access.
"""

from __future__ import annotations

import os
import sys


def _ensure_settings_module() -> None:
    current = (os.environ.get("DJANGO_SETTINGS_MODULE") or "").strip()

    # If CI (or anyone) points to the package, Django won't load INSTALLED_APPS.
    if not current or current == "backend.settings":
        os.environ["DJANGO_SETTINGS_MODULE"] = "backend.settings.dev"


def _create_production_superuser_if_requested() -> None:
    """
    Creates a superuser automatically when RUN_CREATE_SUPERUSER=True.
    Safe to run multiple times (idempotent).
    """

    if os.environ.get("RUN_CREATE_SUPERUSER") != "True":
        return

    import django
    django.setup()

    from django.contrib.auth import get_user_model

    User = get_user_model()

    EMAIL = os.environ.get("AUTO_ADMIN_EMAIL", "admin@tisdocme.com")
    PASSWORD = os.environ.get("AUTO_ADMIN_PASSWORD", "StrongPassword123!")

    if not User.objects.filter(email=EMAIL).exists():
        User.objects.create_superuser(
            email=EMAIL,
            password=PASSWORD,
        )
        print("✔ Production superuser created.")
    else:
        print("✔ Superuser already exists.")


def main() -> None:
    _ensure_settings_module()

    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc

    # Run auto superuser hook before command execution
    _create_production_superuser_if_requested()

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
