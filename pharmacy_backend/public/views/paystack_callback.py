# public/views/paystack_callback.py
"""
PAYSTACK CALLBACK VIEW

Purpose:
- Handles Paystack browser redirect after payment
- Reads reference from query params
- Looks up PaymentAttempt
- Redirects frontend to:
    /store/<store_id>/order/<order_id>

Security hardening:
- FRONTEND_BASE_URL comes from settings (env-driven)
- In production, should be https://your-frontend-domain
- Avoid hardcoding localhost
"""

from __future__ import annotations

from urllib.parse import urlparse

from django.conf import settings
from django.shortcuts import redirect
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from sales.models import PaymentAttempt


def _safe_frontend_base() -> str:
    base = (getattr(settings, "FRONTEND_BASE_URL", "") or "").strip()
    if not base:
        base = "http://localhost:5173"

    parsed = urlparse(base)
    if not parsed.scheme or not parsed.netloc:
        # refuse weird values; fall back to local dev
        return "http://localhost:5173"

    return base.rstrip("/")


class PaystackCallbackView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        reference = request.query_params.get("reference")
        if not reference:
            return redirect(_safe_frontend_base() + "/store")

        attempt = (
            PaymentAttempt.objects.select_related("order")
            .filter(reference=reference)
            .first()
        )

        if not attempt or not attempt.order:
            return redirect(_safe_frontend_base() + "/store")

        order = attempt.order
        store_id = getattr(order, "store_id", None) or getattr(
            getattr(order, "store", None), "id", None
        )
        order_id = getattr(order, "id", None)

        if not store_id or not order_id:
            return redirect(_safe_frontend_base() + "/store")

        frontend_base = _safe_frontend_base()
        return redirect(f"{frontend_base}/store/{store_id}/order/{order_id}")
