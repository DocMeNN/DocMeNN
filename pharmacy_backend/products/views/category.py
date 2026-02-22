# products/views/category.py

from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from permissions.roles import IsPharmacistOrAdmin
from products.models import Category
from products.serializers.category import CategorySerializer


class CategoryViewSet(viewsets.ModelViewSet):
    """
    Category API

    Policy (aligned with Product management):
    - Anyone who can access inventory/product management can also create categories.
    """

    queryset = Category.objects.all().order_by("name")
    serializer_class = CategorySerializer
    permission_classes = [IsAuthenticated, IsPharmacistOrAdmin]