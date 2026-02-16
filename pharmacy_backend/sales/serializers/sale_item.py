from rest_framework import serializers
from sales.models import SaleItem


class SaleItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = SaleItem
        fields = [
            "id",
            "product",
            "quantity",
            "unit_price",
            "line_total",
        ]
        read_only_fields = ["line_total"]
