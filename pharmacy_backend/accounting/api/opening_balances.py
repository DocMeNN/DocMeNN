# accounting/api/opening_balances.py
"""
PATH: accounting/api/opening_balances.py

OPENING BALANCES API VALIDATION

Thin API-layer validation.
Core business rules enforced in domain layer.
"""

from __future__ import annotations

from decimal import Decimal

from rest_framework import serializers


class OpeningBalanceLineSerializer(serializers.Serializer):
    account_code = serializers.CharField()
    dc = serializers.ChoiceField(choices=[("D", "Debit"), ("C", "Credit")])
    amount = serializers.DecimalField(
        max_digits=18,
        decimal_places=2,
        min_value=Decimal("0.01"),
    )


class OpeningBalancesCreateSerializer(serializers.Serializer):
    business_id = serializers.CharField()
    as_of_date = serializers.DateField()
    lines = OpeningBalanceLineSerializer(many=True)

    def validate(self, attrs):
        lines = attrs.get("lines") or []
        if not lines:
            raise serializers.ValidationError("At least one line is required")

        # Prevent duplicate account codes
        codes = [line["account_code"].strip() for line in lines]
        if len(codes) != len(set(codes)):
            raise serializers.ValidationError(
                "Duplicate account_code detected in lines"
            )

        debit = sum(
            (line["amount"] for line in lines if line["dc"] == "D"),
            start=Decimal("0.00"),
        )

        credit = sum(
            (line["amount"] for line in lines if line["dc"] == "C"),
            start=Decimal("0.00"),
        )

        debit = debit.quantize(Decimal("0.01"))
        credit = credit.quantize(Decimal("0.01"))

        if debit != credit:
            raise serializers.ValidationError(
                f"Opening balances must balance. Debits={debit} Credits={credit}"
            )

        return attrs
