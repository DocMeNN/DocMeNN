# manage.py
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
"""

from __future__ import annotations

import os
import sys


def _ensure_settings_module() -> None:
    current = (os.environ.get("DJANGO_SETTINGS_MODULE") or "").strip()

    # If CI (or anyone) points to the package, Django won't load INSTALLED_APPS.
    if not current or current == "backend.settings":
        os.environ["DJANGO_SETTINGS_MODULE"] = "backend.settings.dev"


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

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
