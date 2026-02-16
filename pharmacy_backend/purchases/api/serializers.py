# purchases/api/serializers.py

from rest_framework import serializers

from purchases.models import Supplier, PurchaseInvoice, PurchaseInvoiceItem, SupplierPayment


class SupplierSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supplier
        fields = "__all__"
        read_only_fields = ("id", "created_at")


class PurchaseInvoiceItemCreateSerializer(serializers.Serializer):
    product_id = serializers.UUIDField()
    batch_number = serializers.CharField()
    expiry_date = serializers.DateField()
    quantity = serializers.IntegerField(min_value=1)
    unit_cost = serializers.DecimalField(max_digits=14, decimal_places=2)


class PurchaseInvoiceCreateSerializer(serializers.Serializer):
    supplier_id = serializers.UUIDField()
    invoice_number = serializers.CharField()
    invoice_date = serializers.DateField()
    items = PurchaseInvoiceItemCreateSerializer(many=True)


class PurchaseInvoiceSerializer(serializers.ModelSerializer):
    items = serializers.SerializerMethodField()

    class Meta:
        model = PurchaseInvoice
        fields = "__all__"

    def get_items(self, obj):
        qs = obj.items.select_related("product").all()
        return [
            {
                "id": str(it.id),
                "product_id": str(it.product_id),
                "product_name": getattr(it.product, "name", ""),
                "batch_number": it.batch_number,
                "expiry_date": it.expiry_date,
                "quantity": it.quantity,
                "unit_cost": str(it.unit_cost),
                "line_total": str(it.line_total),
            }
            for it in qs
        ]


class ReceivePurchaseInvoiceSerializer(serializers.Serializer):
    inventory_account_code = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    payable_account_code = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    def validate(self, attrs):
        inv = attrs.get("inventory_account_code")
        ap = attrs.get("payable_account_code")

        if inv is not None and str(inv).strip() == "":
            attrs["inventory_account_code"] = None

        if ap is not None and str(ap).strip() == "":
            attrs["payable_account_code"] = None

        return attrs


class SupplierPaymentCreateSerializer(serializers.Serializer):
    supplier_id = serializers.UUIDField()
    invoice_id = serializers.UUIDField(required=False, allow_null=True)

    payment_date = serializers.DateField(required=False)
    amount = serializers.DecimalField(max_digits=14, decimal_places=2)

    payment_method = serializers.ChoiceField(choices=["cash", "bank"])

    narration = serializers.CharField(required=False, allow_blank=True)

    payable_account_code = serializers.CharField(required=False, allow_blank=True)
    payment_account_code = serializers.CharField(required=False, allow_blank=True)


class SupplierPaymentSerializer(serializers.ModelSerializer):
    supplier_name = serializers.CharField(source="supplier.name", read_only=True)
    invoice_number = serializers.SerializerMethodField()

    class Meta:
        model = SupplierPayment
        fields = [
            "id",
            "supplier",
            "supplier_name",
            "invoice",
            "invoice_number",
            "payment_date",
            "amount",
            "payment_method",
            "narration",
            "created_at",
        ]

    def get_invoice_number(self, obj):
        return getattr(getattr(obj, "invoice", None), "invoice_number", None)
