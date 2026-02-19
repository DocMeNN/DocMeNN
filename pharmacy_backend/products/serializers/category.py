# products/serializers/category.py

from rest_framework import serializers

from products.models import Category


class CategorySerializer(serializers.ModelSerializer):
    """
    Simple Category serializer (read-only for now)
    """

    class Meta:
        model = Category
        fields = ["id", "name", "created_at"]
        read_only_fields = fields
