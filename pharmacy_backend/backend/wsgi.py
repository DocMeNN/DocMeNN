# backend/wsgi.py
"""
WSGI config for backend project.
Defaults to dev settings unless DJANGO_SETTINGS_MODULE is set externally (Render).

Operational hardening:
- Keep this behavior, but in Render you MUST set DJANGO_SETTINGS_MODULE=backend.settings.prod.
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    os.getenv("DJANGO_SETTINGS_MODULE", "backend.settings.dev"),
)

application = get_wsgi_application()