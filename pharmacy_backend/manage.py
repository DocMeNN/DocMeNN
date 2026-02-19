# manage.py
"""
PATH: manage.py

Django management entrypoint.

Critical rule:
- If DJANGO_SETTINGS_MODULE is NOT set, we default to backend.settings.dev.
  This ensures INSTALLED_APPS (including `store`) is defined for CI/test runs.

Production safety:
- Render/production must set DJANGO_SETTINGS_MODULE=backend.settings.prod explicitly.
"""

from __future__ import annotations

import os
import sys


def main() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings.dev")

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
