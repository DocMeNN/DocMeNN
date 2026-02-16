# products/views/category.py

from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from products.models import Category
from products.serializers.category import CategorySerializer


class CategoryViewSet(viewsets.ModelViewSet):
    """
    Category API

    Responsibilities:
    - Create categories
    - List categories
    - Retrieve category details

    Used by:
    - Product creation
    - Filtering / grouping
    """

    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [IsAuthenticated]
