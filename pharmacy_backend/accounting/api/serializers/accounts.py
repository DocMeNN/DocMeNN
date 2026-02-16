# accounting/api/serializers/accounts.py

from rest_framework import serializers
from accounting.models.account import Account


class AccountListSerializer(serializers.ModelSerializer):
    """
    Read-only serializer for listing accounts in the active chart.
    UI needs: code, name, type (and id for keys).
    """

    class Meta:
        model = Account
        fields = ("id", "code", "name", "account_type", "is_active")
        read_only_fields = fields
