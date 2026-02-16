# sales/serializers/refund_command.py

from rest_framework import serializers


class SaleRefundCommandSerializer(serializers.Serializer):
    """
    Command serializer for refund requests.

    This serializer does NOT touch the database.
    It only validates input for the refund action.
    """

    reason = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=255,
    )
