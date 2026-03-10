"""
PATH: store/views/order_views.py

ORDER API VIEWS
"""

from rest_framework.generics import ListCreateAPIView
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status

from store.models import Order
from store.serializers import OrderSerializer
from store.services.order_service import complete_order


class OrderListCreateView(ListCreateAPIView):
    """
    List all orders or create a new one.
    """

    queryset = Order.objects.all()
    serializer_class = OrderSerializer


@api_view(["POST"])
def complete_order_view(request, order_id):
    """
    Complete an order.
    """

    try:
        order = Order.objects.get(id=order_id)

    except Order.DoesNotExist:
        return Response(
            {"error": "Order not found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    complete_order(order)

    return Response(
        {"status": "order completed"},
        status=status.HTTP_200_OK,
    )