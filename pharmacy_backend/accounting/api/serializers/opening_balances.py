# accounting/api/serializers/opening_balances.py

"""
PATH: accounting/api/serializers/opening_balances.py

OPENING BALANCES SERIALIZERS (DRF)

Rule:
- Serializer is responsible for shape validation (types/required fields).
- Domain validation (balance, duplicates, money normalization rules) is delegated to:
  accounting.opening_balance.OpeningBalancePayload

This keeps correctness centralized and prevents drift between layers.
"""

from __future__ import annotations

from decimal import Decimal

from rest_framework import serializers

from accounting.opening_balance import OpeningBalanceError, OpeningBalancePayload


class OpeningBalanceLineSerializer(serializers.Serializer):
    account_code = serializers.CharField()
    dc = serializers.ChoiceField(choices=[("D", "Debit"), ("C", "Credit")])
    amount = serializers.DecimalField(
        max_digits=18,
        decimal_places=2,
        min_value=Decimal("0.01"),
    )

    def validate_account_code(self, value: str):
        v = (value or "").strip()
        if not v:
            raise serializers.ValidationError("account_code is required")
        return v


class OpeningBalancesCreateSerializer(serializers.Serializer):
    business_id = serializers.CharField()
    as_of_date = serializers.DateField()
    lines = OpeningBalanceLineSerializer(many=True)

    def validate_business_id(self, value: str):
        v = (value or "").strip()
        if not v:
            raise serializers.ValidationError("business_id is required")
        return v

    def validate(self, attrs):
        # Delegate business rules validation to the domain layer
        try:
            OpeningBalancePayload.from_raw(
                business_id=attrs.get("business_id"),
                as_of_date=attrs.get("as_of_date"),
                raw_lines=attrs.get("lines") or [],
            )
        except OpeningBalanceError as exc:
            raise serializers.ValidationError(str(exc)) from exc

        return attrs
