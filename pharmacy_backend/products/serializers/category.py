# products/serializers/category.py

from rest_framework import serializers

from products.models import Category


class CategorySerializer(serializers.ModelSerializer):
    """
    Category serializer.

    Rules:
    - name is writable (so staff can create categories)
    - id + created_at are read-only
    """

    name = serializers.CharField(required=True, allow_blank=False, max_length=255)

    class Meta:
        model = Category
        fields = ["id", "name", "created_at"]
        read_only_fields = ["id", "created_at"]

    def validate_name(self, value: str):
        v = (value or "").strip()
        if not v:
            raise serializers.ValidationError("name cannot be blank")
        return v