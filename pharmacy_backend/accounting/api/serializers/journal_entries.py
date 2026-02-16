# accounting/api/serializers/journal_entries.py

from rest_framework import serializers

from accounting.models.journal import JournalEntry


class JournalEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = JournalEntry
        fields = "__all__"
        read_only_fields = ("id",)
