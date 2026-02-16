# store/view.py

from django.shortcuts import render

# Create your views here.
from rest_framework import generics, status, permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Order, OrderItem
from .serializers import OrderSerializer, OrderItemSerializer
from products.models import Product


# -----------------------------
#   PERMISSIONS
# -----------------------------
class IsAdminOrOwner(permissions.BasePermission):
    """
    Allow only:
    - Admins (staff)
    - The owner of the order
    """
    def has_object_permission(self, request, view, obj):
        return (
            request.user.is_staff or
            obj.customer == request.user
        )


# -----------------------------
#   CREATE & LIST ORDERS
# -----------------------------
class OrderListCreateView(generics.ListCreateAPIView):
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_staff:
            return Order.objects.all().order_by('-created_at')
        return Order.objects.filter(customer=user).order_by('-created_at')

    def perform_create(self, serializer):
        serializer.save(customer=self.request.user)


# -----------------------------
#   ORDER DETAIL VIEW
# -----------------------------
class OrderDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = OrderSerializer
    queryset = Order.objects.all()
    permission_classes = [permissions.IsAuthenticated, IsAdminOrOwner]


# -----------------------------
#   ADD ITEM TO ORDER
# -----------------------------
class AddOrderItemView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, order_id):
        try:
            order = Order.objects.get(id=order_id)
        except Order.DoesNotExist:
            return Response({"error": "Order not found"}, status=404)

        # Only owner or admin may add items
        if not (request.user.is_staff or order.customer == request.user):
            return Response({"error": "Not allowed"}, status=403)

        product_id = request.data.get("product")
        quantity = int(request.data.get("quantity", 1))

        if not product_id:
            return Response({"error": "product is required"}, status=400)

        try:
            product = Product.objects.get(id=product_id)
        except Product.DoesNotExist:
            return Response({"error": "Product not found"}, status=404)

        unit_price = product.unit_price
        total_price = unit_price * quantity

        item = OrderItem.objects.create(
            order=order,
            product=product,
            quantity=quantity,
            unit_price=unit_price,
            total_price=total_price,
        )

        # Recalculate order total
        total = sum(i.total_price for i in order.items.all())
        order.total_amount = total
        order.save()

        return Response(OrderItemSerializer(item).data, status=201)
