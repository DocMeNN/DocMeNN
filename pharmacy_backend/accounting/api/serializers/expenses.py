# accounting/api/serializers/expenses.py

from rest_framework import serializers

from accounting.models.expense import Expense


class ExpenseSerializer(serializers.ModelSerializer):
    """
    Output serializer (DB truth) - clean, stable contract.
    """

    expense_account_code = serializers.CharField(
        source="expense_account.code", read_only=True
    )
    expense_account_name = serializers.CharField(
        source="expense_account.name", read_only=True
    )
    payment_account_code = serializers.CharField(
        source="payment_account.code", read_only=True
    )
    payment_account_name = serializers.CharField(
        source="payment_account.name", read_only=True
    )
    posted_journal_entry_id = serializers.UUIDField(
        source="posted_journal_entry.id", read_only=True
    )

    class Meta:
        model = Expense
        fields = [
            "id",
            "expense_date",
            "amount",
            "payment_method",
            "vendor",
            "narration",
            "is_posted",
            "posted_journal_entry_id",
            "created_at",
            "expense_account_code",
            "expense_account_name",
            "payment_account_code",
            "payment_account_name",
        ]
        read_only_fields = (
            "id",
            "is_posted",
            "posted_journal_entry_id",
            "created_at",
            "expense_account_code",
            "expense_account_name",
            "payment_account_code",
            "payment_account_name",
        )


class ExpenseCreateSerializer(serializers.Serializer):
    """
    Input serializer (Swagger-visible).
    """

    expense_date = serializers.DateField(required=False)
    amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    expense_account_code = serializers.CharField()

    payment_method = serializers.ChoiceField(choices=["cash", "bank", "credit"])
    payable_account_code = serializers.CharField(
        required=False, allow_blank=True, allow_null=True
    )

    vendor = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    narration = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    def validate_amount(self, value):
        if value is None:
            raise serializers.ValidationError("amount is required")
        if value <= 0:
            raise serializers.ValidationError("amount must be > 0")
        return value

    def validate_expense_account_code(self, value):
        v = (value or "").strip()
        if not v:
            raise serializers.ValidationError("expense_account_code is required")
        return v

    def validate(self, attrs):
        method = (attrs.get("payment_method") or "").strip().lower()
        attrs["payment_method"] = method

        for k in ("vendor", "narration"):
            if k in attrs and attrs[k] is not None:
                attrs[k] = str(attrs[k]).strip()
            else:
                attrs[k] = ""

        payable = attrs.get("payable_account_code")
        if payable is not None:
            payable = str(payable).strip()
            attrs["payable_account_code"] = payable or None

        if method != "credit":
            attrs["payable_account_code"] = None

        return attrs
