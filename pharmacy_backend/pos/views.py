# pharmacy_backend/pos/views.py

import uuid

from django.db import transaction
from django.shortcuts import get_object_or_404

from rest_framework import generics, status
from rest_framework.response import Response

from permissions.roles import (
    IsPharmacist,
    IsCashier,
    IsReception,
    IsStaff,
)

from .models import POSCart, POSCartItem
from .serializers import POSCartSerializer, POSCartItemSerializer

from products.models import Product
from products.services.stock_fifo import (
    deduct_stock_fifo,
    InsufficientStockError,
)

from sales.models import Sale, SaleItem


# ---------------------- HELPERS ----------------------
def get_cart(user):
    """
    Returns the active POS cart for a user.
    Creates one if it does not exist.
    """
    cart, _ = POSCart.objects.get_or_create(user=user)
    return cart


# ---------------------- VIEW CART ----------------------
class POSCartView(generics.RetrieveAPIView):
    """
    View active POS cart

    Allowed:
    - Pharmacist
    - Cashier
    - Reception (view-only)
    """

    serializer_class = POSCartSerializer
    permission_classes = [IsPharmacist | IsCashier | IsReception]

    def get_object(self):
        return get_cart(self.request.user)


# ---------------------- ADD TO CART ----------------------
class AddToCartView(generics.CreateAPIView):
    """
    Add product to POS cart

    Allowed:
    - Any staff member

    NOTES:
    - Stock is validated only
    - Actual deduction happens at checkout
    """

    serializer_class = POSCartItemSerializer
    permission_classes = [IsStaff]

    def post(self, request, *args, **kwargs):
        cart = get_cart(request.user)

        product_id = request.data.get("product")
        quantity = int(request.data.get("quantity", 1))

        if quantity <= 0:
            return Response(
                {"error": "Quantity must be greater than zero"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        product = get_object_or_404(Product, id=product_id)

        # Read-only stock validation
        if product.total_stock < quantity:
            return Response(
                {
                    "error": "Insufficient stock",
                    "available": product.total_stock,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        item, created = POSCartItem.objects.get_or_create(
            cart=cart,
            product=product,
            defaults={"quantity": quantity},
        )

        if not created:
            new_quantity = item.quantity + quantity

            if product.total_stock < new_quantity:
                return Response(
                    {
                        "error": "Insufficient stock for requested quantity",
                        "available": product.total_stock,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            item.quantity = new_quantity
            item.save()

        return Response(
            POSCartSerializer(cart).data,
            status=status.HTTP_200_OK,
        )


# ---------------------- REMOVE FROM CART ----------------------
class RemoveFromCartView(generics.DestroyAPIView):
    """
    Remove item from POS cart
    """

    permission_classes = [IsStaff]

    def delete(self, request, pk, *args, **kwargs):
        cart = get_cart(request.user)

        item = get_object_or_404(
            POSCartItem,
            id=pk,
            cart=cart,
        )

        item.delete()

        return Response(
            {"message": "Item removed from cart"},
            status=status.HTTP_200_OK,
        )


# ---------------------- CHECKOUT ----------------------
class CheckoutView(generics.GenericAPIView):
    """
    Checkout POS cart

    Allowed:
    - Pharmacist
    - Cashier

    GUARANTEES:
    - Atomic transaction
    - FIFO batch deduction
    - StockMovement audit
    - Sale is created ONLY if stock deduction succeeds
    """

    permission_classes = [IsPharmacist | IsCashier]

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        user = request.user
        cart = get_cart(user)

        if not cart.items.exists():
            return Response(
                {"error": "Cart is empty"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        payment_method = request.data.get("payment_method", "cash").lower()
        receipt_no = f"RCPT-{uuid.uuid4().hex[:8].upper()}"

        cart_items = cart.items.select_related("product")

        total_amount = 0

        # Final safety validation
        for item in cart_items:
            if item.product.total_stock < item.quantity:
                return Response(
                    {
                        "error": f"Insufficient stock for {item.product.name}",
                        "available": item.product.total_stock,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            total_amount += item.quantity * item.product.unit_price

        # Create sale header
        sale = Sale.objects.create(
            user=user,
            total_amount=total_amount,
            payment_method=payment_method,
            receipt_no=receipt_no,
        )

        try:
            # FIFO deduction + audit logging
            for item in cart_items:
                deduct_stock_fifo(
                    product=item.product,
                    quantity=item.quantity,
                    user=user,
                    sale=sale,
                )

                SaleItem.objects.create(
                    sale=sale,
                    product=item.product,
                    quantity=item.quantity,
                    price=item.product.unit_price,
                )

        except InsufficientStockError as exc:
            transaction.set_rollback(True)
            return Response(
                {"error": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Clear cart only after successful checkout
        cart.items.all().delete()

        return Response(
            {
                "message": "Checkout successful",
                "sale_id": sale.id,
                "receipt_no": receipt_no,
                "total_amount": sale.total_amount,
            },
            status=status.HTTP_201_CREATED,
        )
