# PATH: public/serializers.py

"""
PATH: public/serializers.py

PUBLIC SERIALIZERS (ONLINE STORE)

Purpose:
- Single, shared schema contracts for Public API endpoints.
- Keeps public/views thin and consistent (no duplicated serializer definitions).

Used by:
- public/views/checkout.py   (LEGACY V1 checkout + receipt)
- public/views/orders.py     (Paystack initiate / status endpoints)
- public/views/webhooks.py   (Paystack webhook ack)

Notes:
- These serializers are deliberately "transport layer" only:
  they validate request/response shapes, not business rules.
"""

from __future__ import annotations

from rest_framework import serializers


class PublicCartItemSerializer(serializers.Serializer):
    product_id = serializers.UUIDField()
    quantity = serializers.IntegerField(min_value=1)


class PublicCustomerSerializer(serializers.Serializer):
    customer_name = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    customer_phone = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    customer_email = serializers.EmailField(required=False, allow_blank=True, allow_null=True)


class PublicOrderInitiateSerializer(serializers.Serializer):
    """
    Phase 4 contract:
    Create an OnlineOrder (PENDING_PAYMENT) then initiate Paystack payment.
    """
    store_id = serializers.UUIDField()
    items = PublicCartItemSerializer(many=True)

    # Optional customer fields (nice to have)
    customer_name = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    customer_phone = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    customer_email = serializers.EmailField(required=False, allow_blank=True, allow_null=True)


class PublicOrderInitiateResponseSerializer(serializers.Serializer):
    """
    Response to frontend:
    - order_id + order_no for tracking
    - authorization_url for redirect
    - reference for support/debug (not secret)
    """
    order_id = serializers.UUIDField()
    order_no = serializers.CharField()
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    currency = serializers.CharField()
    provider = serializers.CharField()
    reference = serializers.CharField()
    authorization_url = serializers.URLField()


class PublicOrderStatusResponseSerializer(serializers.Serializer):
    """
    Used for polling from frontend:
    - pending_payment / paid / fulfilled / cancelled / expired
    """
    order_id = serializers.UUIDField()
    order_no = serializers.CharField()
    status = serializers.CharField()
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    currency = serializers.CharField()
    paid_at = serializers.DateTimeField(allow_null=True, required=False)
    sale_id = serializers.UUIDField(allow_null=True, required=False)


class PublicWebhookAckSerializer(serializers.Serializer):
    """
    Simple webhook acknowledgement (Paystack expects a 200).
    """
    ok = serializers.BooleanField()
    detail = serializers.CharField(required=False, allow_blank=True)