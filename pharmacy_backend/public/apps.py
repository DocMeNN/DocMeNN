# public/apps.py

"""
PUBLIC APP CONFIG

Public Online Store (AllowAny) module:
- Store listing (future)
- Product catalog (future)
- Checkout + receipt (V1)

Golden Rule:
- This file carries its own path header for copy/paste clarity.
"""

from django.apps import AppConfig


class PublicConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "public"
    verbose_name = "Public Online Store"
