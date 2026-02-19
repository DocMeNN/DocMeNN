# purchases/api/views.py

from django.db import IntegrityError, transaction
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from products.models.product import Product
from purchases.api.serializers import (
    PurchaseInvoiceCreateSerializer,
    PurchaseInvoiceSerializer,
    ReceivePurchaseInvoiceSerializer,
    SupplierPaymentCreateSerializer,
    SupplierPaymentSerializer,
    SupplierSerializer,
)
from purchases.models import (
    PurchaseInvoice,
    PurchaseInvoiceItem,
    Supplier,
    SupplierPayment,
)
from purchases.services.payment_service import (
    SupplierPaymentError,
    pay_supplier_invoice,
)
from purchases.services.receiving_service import (
    PurchaseReceivingError,
    receive_purchase_invoice,
)


class SupplierListCreateView(GenericAPIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=["purchases"], responses=SupplierSerializer(many=True))
    def get(self, request):
        qs = Supplier.objects.filter(is_active=True).order_by("name")
        return Response(
            SupplierSerializer(qs, many=True).data, status=status.HTTP_200_OK
        )

    @extend_schema(
        tags=["purchases"],
        request=SupplierSerializer,
        responses={201: SupplierSerializer},
    )
    def post(self, request):
        s = SupplierSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        supplier = s.save()
        return Response(
            SupplierSerializer(supplier).data, status=status.HTTP_201_CREATED
        )


class PurchaseInvoiceListCreateView(GenericAPIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=["purchases"], responses=PurchaseInvoiceSerializer(many=True))
    def get(self, request):
        qs = (
            PurchaseInvoice.objects.select_related("supplier")
            .prefetch_related("items", "items__product")
            .order_by("-created_at")
        )
        return Response(
            PurchaseInvoiceSerializer(qs, many=True).data, status=status.HTTP_200_OK
        )

    @extend_schema(
        tags=["purchases"],
        request=PurchaseInvoiceCreateSerializer,
        responses={201: PurchaseInvoiceSerializer},
    )
    @transaction.atomic
    def post(self, request):
        s = PurchaseInvoiceCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        data = s.validated_data

        try:
            supplier = Supplier.objects.get(id=data["supplier_id"], is_active=True)
        except Supplier.DoesNotExist:
            return Response(
                {"detail": "Supplier not found"}, status=status.HTTP_400_BAD_REQUEST
            )

        try:
            invoice = PurchaseInvoice.objects.create(
                supplier=supplier,
                invoice_number=data["invoice_number"],
                invoice_date=data["invoice_date"],
                status=PurchaseInvoice.STATUS_DRAFT,
            )
        except IntegrityError:
            return Response(
                {"detail": "Invoice number already exists for this supplier"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        for line in data["items"]:
            try:
                product = Product.objects.get(id=line["product_id"])
            except Product.DoesNotExist:
                return Response(
                    {"detail": f"Product not found: {line['product_id']}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            PurchaseInvoiceItem.objects.create(
                invoice=invoice,
                product=product,
                batch_number=line["batch_number"],
                expiry_date=line["expiry_date"],
                quantity=line["quantity"],
                unit_cost=line["unit_cost"],
            )

        invoice = (
            PurchaseInvoice.objects.select_related("supplier")
            .prefetch_related("items", "items__product")
            .get(id=invoice.id)
        )
        return Response(
            PurchaseInvoiceSerializer(invoice).data, status=status.HTTP_201_CREATED
        )


class PurchaseInvoiceReceiveView(GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ReceivePurchaseInvoiceSerializer

    @extend_schema(tags=["purchases"], request=ReceivePurchaseInvoiceSerializer)
    def post(self, request, invoice_id):
        s = self.get_serializer(data=request.data)
        s.is_valid(raise_exception=True)
        data = s.validated_data

        try:
            result = receive_purchase_invoice(
                invoice_id=invoice_id,
                inventory_account_code=data.get("inventory_account_code"),
                payable_account_code=data.get("payable_account_code"),
            )
        except PurchaseReceivingError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(result, status=status.HTTP_201_CREATED)


class SupplierPaymentListCreateView(GenericAPIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=["purchases"], responses=SupplierPaymentSerializer(many=True))
    def get(self, request):
        qs = SupplierPayment.objects.select_related("supplier", "invoice").order_by(
            "-created_at"
        )
        return Response(
            SupplierPaymentSerializer(qs, many=True).data, status=status.HTTP_200_OK
        )

    @extend_schema(tags=["purchases"], request=SupplierPaymentCreateSerializer)
    def post(self, request):
        s = SupplierPaymentCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        data = s.validated_data

        try:
            result = pay_supplier_invoice(
                supplier_id=data["supplier_id"],
                invoice_id=data.get("invoice_id"),
                payment_date=data.get("payment_date"),
                amount=data["amount"],
                payment_method=data["payment_method"],
                narration=data.get("narration", ""),
                payable_account_code=data.get("payable_account_code"),
                payment_account_code=data.get("payment_account_code"),
            )
        except SupplierPaymentError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(result, status=status.HTTP_201_CREATED)
