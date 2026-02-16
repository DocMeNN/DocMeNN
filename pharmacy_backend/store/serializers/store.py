from rest_framework import serializers

from store.models import Store


class StoreSerializer(serializers.ModelSerializer):
    """
    Serializer for pharmacy store / branch.
    """

    class Meta:
        model = Store
        fields = [
            "id",
            "name",
            "code",
            "address",
            "phone",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
        ]
