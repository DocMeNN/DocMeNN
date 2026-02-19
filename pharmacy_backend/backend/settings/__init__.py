# backend/settings/__init__.py
"""
PATH: backend/settings/__init__.py

Settings package entrypoint.

We intentionally do NOT import dev/prod here to avoid accidental environment coupling.
Use DJANGO_SETTINGS_MODULE to select:
- backend.settings.dev   (local development)
- backend.settings.prod  (production on Render)
"""
