from django.urls import path
from .views import (
    OrderListCreateView,
    OrderDetailView,
    AddOrderItemView,
)

urlpatterns = [
    path('orders/', OrderListCreateView.as_view(), name='order-list-create'),
    path('orders/<uuid:pk>/', OrderDetailView.as_view(), name='order-detail'),
    path('orders/<uuid:order_id>/add-item/', AddOrderItemView.as_view(), name='order-add-item'),
]
