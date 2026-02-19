from rest_framework import permissions, viewsets

from batches.models import Batch
from batches.serializers import BatchSerializer


class BatchViewSet(viewsets.ModelViewSet):
    """
    API endpoint for managing product batches.
    """

    queryset = Batch.objects.select_related("product").all()
    serializer_class = BatchSerializer
    permission_classes = [permissions.IsAuthenticated]
