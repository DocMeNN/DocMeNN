# accounting/api/serializers/close_period.py

"""
======================================================
PATH: accounting/api/serializers/close_period.py
======================================================
CLOSE PERIOD SERIALIZER

Validates inputs for closing an accounting period.

Rules:
- start_date and end_date are required
- start_date must be <= end_date
- retained_earnings_account_code is optional; blank -> None
"""

from rest_framework import serializers


class ClosePeriodSerializer(serializers.Serializer):
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    retained_earnings_account_code = serializers.CharField(
        required=False, allow_blank=True, allow_null=True
    )

    def validate(self, attrs):
        start = attrs["start_date"]
        end = attrs["end_date"]

        if start > end:
            raise serializers.ValidationError(
                {"end_date": "end_date must be >= start_date"}
            )

        code = attrs.get("retained_earnings_account_code")
        if code is not None and str(code).strip() == "":
            attrs["retained_earnings_account_code"] = None

        return attrs
