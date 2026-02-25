from __future__ import annotations

import logging
from urllib.parse import urlparse

from django.conf import settings
from django.shortcuts import redirect
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from sales.models import PaymentAttempt

logger = logging.getLogger(__name__)


def _safe_frontend_base() -> str:
    base = (getattr(settings, "FRONTEND_BASE_URL", "") or "").strip()
    if not base:
        base = "http://localhost:5173"

    parsed = urlparse(base)
    if not parsed.scheme or not parsed.netloc:
        logger.warning("Invalid FRONTEND_BASE_URL detected")
        return "http://localhost:5173"

    return base.rstrip("/")


class PaystackCallbackView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        reference = request.query_params.get("reference")

        if not reference:
            logger.warning("Callback without reference")
            return redirect(_safe_frontend_base() + "/store")

        attempt = (
            PaymentAttempt.objects.select_related("order")
            .filter(reference=reference)
            .first()
        )

        if not attempt or not attempt.order:
            logger.warning("Callback unknown reference", extra={"reference": reference})
            return redirect(_safe_frontend_base() + "/store")

        order = attempt.order
        store_id = getattr(order, "store_id", None) or getattr(
            getattr(order, "store", None), "id", None
        )
        order_id = getattr(order, "id", None)

        if not store_id or not order_id:
            logger.warning("Callback missing store/order id", extra={"reference": reference})
            return redirect(_safe_frontend_base() + "/store")

        frontend_base = _safe_frontend_base()
        logger.info("Callback redirecting to frontend", extra={"reference": reference})

        return redirect(f"{frontend_base}/store/{store_id}/order/{order_id}")