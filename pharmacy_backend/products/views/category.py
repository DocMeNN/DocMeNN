# products/views/category.py

from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from permissions.roles import HasAnyCapability, CAP_INVENTORY_EDIT
from products.models import Category
from products.serializers.category import CategorySerializer


class CategoryViewSet(viewsets.ModelViewSet):
    """
    Category API

    Policy:
    - Any authenticated user can READ categories (needed for product forms)
    - Only users with inventory edit capability can CREATE/UPDATE/DELETE categories
      (this aligns with "can add product" or "can intake stock").
    """

    queryset = Category.objects.all().order_by("name")
    serializer_class = CategorySerializer

    def get_permissions(self):
        # Allow all authenticated users to list/retrieve (dropdown needs this)
        if self.action in {"list", "retrieve"}:
            return [IsAuthenticated()]

        # Writes require inventory.edit capability
        self.required_any_capabilities = {CAP_INVENTORY_EDIT}
        return [IsAuthenticated(), HasAnyCapability()]