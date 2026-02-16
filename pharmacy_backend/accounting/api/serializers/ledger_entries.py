# accounting/api/serializers/ledger_entries.py

from rest_framework import serializers

from accounting.models.ledger import LedgerEntry


class LedgerEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = LedgerEntry
        fields = "__all__"
        read_only_fields = ("id",)
