from rest_framework import serializers
from batches.models import Batch


class BatchSerializer(serializers.ModelSerializer):
    is_expired = serializers.ReadOnlyField()
    is_out_of_stock = serializers.ReadOnlyField()

    class Meta:
        model = Batch
        fields = [
            "id",
            "product",
            "batch_number",
            "expiry_date",
            "quantity",
            "is_expired",
            "is_out_of_stock",
            "created_at",
        ]
