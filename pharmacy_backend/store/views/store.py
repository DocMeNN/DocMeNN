# store/views/store.py

"""
STORE VIEWSET

Purpose:
- Staff store management (authenticated)
- Public store listing for Online Store V1 (AllowAny)

Public endpoint:
- GET /api/store/stores/public/
"""

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from permissions.roles import IsStaff  # swap if you want tighter
from store.models.store import Store
from store.serializers.store import StoreSerializer


class StoreViewSet(viewsets.ModelViewSet):
    """
    Store / Branch API
    """

    queryset = Store.objects.all().order_by("name")
    serializer_class = StoreSerializer
    permission_classes = [IsAuthenticated, IsStaff]

    @action(
        detail=False,
        methods=["get"],
        url_path="public",
        permission_classes=[AllowAny],
    )
    def public(self, request):
        """
        GET /api/store/stores/public/

        Rules:
        - AllowAny
        - Only active stores
        - Minimal fields (serializer already controls output)
        """
        qs = Store.objects.filter(is_active=True).order_by("name")
        data = StoreSerializer(qs, many=True).data
        return Response(
            {"count": len(data), "results": data}, status=status.HTTP_200_OK
        )
