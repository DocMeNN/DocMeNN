# sales/serializers/refund_read.py

from rest_framework import serializers

from sales.models import SaleRefundAudit


class SaleRefundAuditReadSerializer(serializers.ModelSerializer):
    """
    Read-only serializer for refund audit records.

    Used for:
    - Sale detail views
    - Refund history inspection
    """

    class Meta:
        model = SaleRefundAudit
        fields = [
            "id",
            "sale",
            "reason",
            "original_total_amount",
            "refunded_at",
        ]
        read_only_fields = fields
