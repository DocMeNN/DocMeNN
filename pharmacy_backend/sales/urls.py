# sales/urls.py

"""
COMPAT WRAPPER

Canonical sales endpoints now live in:
- sales/api/urls.py

This file exists so older imports don't break.
"""

from sales.api.urls import urlpatterns  # noqa: F401
