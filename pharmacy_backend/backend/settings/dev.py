# backend/settings/dev.py
"""
PATH: backend/settings/dev.py

LOCAL DEVELOPMENT SETTINGS
Safe + convenient defaults.
"""

from __future__ import annotations

from .base import env

DEBUG = True

ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])

CORS_ALLOWED_ORIGINS = env.list(
    "CORS_ALLOWED_ORIGINS", default=["http://localhost:5173"]
)

CSRF_TRUSTED_ORIGINS = env.list(
    "CSRF_TRUSTED_ORIGINS", default=["http://localhost:5173"]
)

CORS_ALLOW_CREDENTIALS = True
