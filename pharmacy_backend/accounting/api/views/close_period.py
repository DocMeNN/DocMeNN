# PATH: accounting/api/views/close_period.py

"""
PATH: accounting/api/views/close_period.py

PERIOD CLOSE API (PHASE 5 HARDENED)

Purpose:
- Close an accounting period
- Post retained earnings journal
- Lock the period against further postings

Security:
- Authenticated
- Requires explicit permission:
    accounting.add_periodclose
"""

from decimal import Decimal, InvalidOperation

from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounting.api.serializers.close_period import ClosePeriodSerializer
from accounting.services.period_close_service import PeriodCloseError, close_period

# Django auto permission on PeriodClose model
PERIOD_CLOSE_PERMISSION = "accounting.add_periodclose"


def _safe_float(v) -> float:
    try:
        if isinstance(v, Decimal):
            return float(v)
        return float(Decimal(str(v)))
    except (InvalidOperation, ValueError, TypeError):
        return 0.0


class ClosePeriodView(GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ClosePeriodSerializer

    @extend_schema(
        tags=["accounting"],
        request=ClosePeriodSerializer,
        responses={201: dict, 400: dict, 403: dict},
    )
    def post(self, request, *args, **kwargs):
        # ✅ Phase 5 RBAC (strict, no try/except ambiguity)
        if not request.user.has_perm(PERIOD_CLOSE_PERMISSION):
            return Response(
                {"detail": "You do not have permission to close accounting periods."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            result = close_period(
                start_date=data["start_date"],
                end_date=data["end_date"],
                retained_earnings_account_code=data.get(
                    "retained_earnings_account_code"
                ),
            )
        except PeriodCloseError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        je = result["journal_entry"]

        return Response(
            {
                "journal_entry": {
                    "id": str(je.id),
                    "description": je.description,
                    "reference": je.reference,
                    "posted_at": je.posted_at.isoformat() if je.posted_at else None,
                    "is_posted": bool(getattr(je, "is_posted", True)),
                },
                "summary": {
                    "total_revenue": str(result["total_revenue"]),
                    "total_expenses": str(result["total_expenses"]),
                    "net_profit": str(result["net_profit"]),
                    "total_revenue_number": _safe_float(result["total_revenue"]),
                    "total_expenses_number": _safe_float(result["total_expenses"]),
                    "net_profit_number": _safe_float(result["net_profit"]),
                },
            },
            status=status.HTTP_201_CREATED,
        )
