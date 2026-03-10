"""
PATH: backend/events/admin.py
"""

from django.contrib import admin

from backend.events.models import EventOutbox


@admin.register(EventOutbox)
class EventOutboxAdmin(admin.ModelAdmin):

    list_display = (
        "id",
        "event_type",
        "processed",
        "created_at",
        "processed_at",
    )

    list_filter = ("processed",)

    search_fields = ("event_type",)