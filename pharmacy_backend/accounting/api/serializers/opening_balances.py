# accounting/api/serializers/opening_balances.py
"""

OPENING BALANCES SERIALIZERS

Notes:
- API layer validates using the framework-agnostic domain rules.
- Keeps DRF validation thin and consistent with service/domain enforcement.
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


class OpeningBalancesCreateSerializer(serializers.Serializer):
    business_id = serializers.CharField()
    as_of_date = serializers.DateField()
    lines = OpeningBalanceLineSerializer(many=True)

    def validate(self, attrs):
        business_id = attrs.get("business_id")
        as_of_date = attrs.get("as_of_date")
        lines = attrs.get("lines") or []

        try:
            # Domain performs:
            # - required fields
            # - dc validation
            # - amount > 0
            # - duplicate account codes
            # - debit == credit
            payload = OpeningBalancePayload.from_raw(
                business_id=business_id,
                as_of_date=as_of_date,
                raw_lines=lines,
            )
        except OpeningBalanceError as exc:
            raise serializers.ValidationError(str(exc)) from exc

        # Normalize lines back into serializer-friendly dict form (2dp ensured)
        attrs["lines"] = [
            {
                "account_code": line.account_code,
                "dc": line.dc,
                "amount": line.amount,
            }
            for line in payload.lines
        ]

        return attrs
