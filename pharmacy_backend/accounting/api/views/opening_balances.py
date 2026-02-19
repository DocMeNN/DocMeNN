# PATH: accounting/api/views/opening_balances.py

"""
PATH: accounting/api/views/opening_balances.py

OPENING BALANCES API

POST:
- Validates request via serializer (shape + domain rules)
- Calls service which posts an immutable, balanced JournalEntry

Security:
- Authenticated (baseline)
- Phase 5: requires explicit permission to post opening balances
- Phase 5: tenant safety (ENFORCED): user must be allowed for business_id (superuser override)
"""

from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounting.api.serializers.opening_balances import OpeningBalancesCreateSerializer
from accounting.services.account_resolver import user_can_access_business
from accounting.services.opening_balances_service import (
    OpeningBalancesError,
    create_opening_balances,
)

OPENING_BALANCE_PERMISSION = "accounting.add_journalentry"


class OpeningBalancesCreateView(GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = OpeningBalancesCreateSerializer

    @extend_schema(
        tags=["accounting"],
        request=OpeningBalancesCreateSerializer,
        responses={201: dict, 400: dict, 403: dict},
    )
    def post(self, request, *args, **kwargs):
        # ✅ Permission gate (matrix: Opening Balance -> accounting.add_journalentry)
        if not request.user.has_perm(OPENING_BALANCE_PERMISSION):
            return Response(
                {"detail": "You do not have permission to post opening balances."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        business_id = data["business_id"]

        # ✅ Tenant isolation (Phase 5 final lock)
        if not user_can_access_business(request.user, business_id):
            return Response(
                {
                    "detail": "You are not allowed to post opening balances for this business."
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            journal_entry = create_opening_balances(
                business_id=business_id,
                as_of_date=data["as_of_date"],
                raw_lines=data["lines"],
            )
        except OpeningBalancesError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        reference = getattr(journal_entry, "reference", None)
        return Response(
            {
                "id": str(journal_entry.id),
                "description": getattr(journal_entry, "description", ""),
                "reference": reference,
                "posted_at": journal_entry.posted_at.isoformat()
                if journal_entry.posted_at
                else None,
                "is_posted": bool(getattr(journal_entry, "is_posted", True)),
            },
            status=status.HTTP_201_CREATED,
        )
