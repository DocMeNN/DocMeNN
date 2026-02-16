# PATH: public/views/paystack_callback.py

"""
PAYSTACK CALLBACK VIEW

Purpose:
- Handles Paystack browser redirect after payment
- Reads reference from query params
- Looks up PaymentAttempt
- Redirects frontend to:
    /store/<store_id>/order/<order_id>
"""

from django.shortcuts import redirect
from django.conf import settings
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny

from sales.models import PaymentAttempt


class PaystackCallbackView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        reference = request.query_params.get("reference")
        if not reference:
            return redirect("/store")

        attempt = (
            PaymentAttempt.objects
            .select_related("order")
            .filter(reference=reference)
            .first()
        )

        if not attempt or not attempt.order:
            return redirect("/store")

        order = attempt.order
        store_id = getattr(order, "store_id", None) or getattr(order.store, "id", None)
        order_id = order.id

        frontend_base = "http://localhost:5173"

        return redirect(
            f"{frontend_base}/store/{store_id}/order/{order_id}"
        )