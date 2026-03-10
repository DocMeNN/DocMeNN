"""
PATH: store/views/product_views.py

PRODUCT + INVENTORY API VIEWS

Responsibilities
- Adjust product inventory
- Receive purchase goods into inventory
"""

from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status

from store.models import Product, PurchaseInvoice
from store.services.inventory_service import adjust_stock
from store.services.purchase_service import receive_goods


@api_view(["POST"])
def adjust_product_stock(request, product_id):
    """
    Adjust stock quantity for a product.
    """

    quantity_delta = int(request.data.get("quantity_delta", 0))
    batch_id = request.data.get("batch_id")

    try:
        product = Product.objects.get(id=product_id)

    except Product.DoesNotExist:
        return Response(
            {"error": "Product not found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    adjust_stock(
        product=product,
        batch_id=batch_id,
        quantity_delta=quantity_delta,
    )

    return Response(
        {"status": "stock updated"},
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
def receive_goods_view(request, invoice_id):
    """
    Mark purchase invoice as received and update inventory.
    """

    try:
        invoice = PurchaseInvoice.objects.get(id=invoice_id)

    except PurchaseInvoice.DoesNotExist:
        return Response(
            {"error": "Invoice not found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    receive_goods(invoice)

    return Response(
        {"status": "goods received"},
        status=status.HTTP_200_OK,
    )