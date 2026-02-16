# backend/asgi.py
"""
PATH: backend/asgi.py

ASGI config for backend project.
Defaults to dev settings unless DJANGO_SETTINGS_MODULE is set externally (Render).
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    os.getenv("DJANGO_SETTINGS_MODULE", "backend.settings.dev"),
)

application = get_asgi_application()