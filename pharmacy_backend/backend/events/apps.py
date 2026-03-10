"""
PATH: backend/events/apps.py
"""

from django.apps import AppConfig


class EventsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "backend.events"
    verbose_name = "Event System"

    def ready(self):
        """
        Import handlers when Django app registry is ready.

        This ensures event handlers register safely
        after Django finishes loading apps.
        """
        import backend.events.handlers  # noqa