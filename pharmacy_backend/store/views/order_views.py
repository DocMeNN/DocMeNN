from rest_framework.generics import ListCreateAPIView
from store.models import Order
from store.serializers import OrderSerializer


class OrderListCreateView(ListCreateAPIView):
    queryset = Order.objects.all()
    serializer_class = OrderSerializer
