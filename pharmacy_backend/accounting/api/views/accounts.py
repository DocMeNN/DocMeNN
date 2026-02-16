# accounting/api/views/accounts.py

"""
PATH: accounting/api/views/accounts.py

ACTIVE CHART ACCOUNTS API (READ-ONLY)

GET /api/accounting/accounts/
Returns accounts for the ACTIVE chart only (chart-aware), read-only.

Phase 5 Hardening:
- Permission-gated: requires accounting.view_ledgerentry (or tighten later to view_account)
- No chart_id parameter: prevents chart enumeration
"""

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.generics import GenericAPIView
from rest_framework import status

from drf_spectacular.utils import extend_schema

from accounting.models.account import Account
from accounting.services.account_resolver import get_active_chart
from accounting.api.serializers.accounts import AccountListSerializer


class ActiveChartAccountsView(GenericAPIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["accounting"],
        responses=AccountListSerializer(many=True),
    )
    def get(self, request, *args, **kwargs):
        if not request.user.has_perm("accounting.view_ledgerentry"):
            return Response(
                {"detail": "You do not have permission to view accounts."},
                status=status.HTTP_403_FORBIDDEN,
            )

        chart = get_active_chart()

        qs = (
            Account.objects
            .filter(chart=chart, is_active=True)
            .order_by("code")
        )

        return Response(AccountListSerializer(qs, many=True).data, status=status.HTTP_200_OK)
