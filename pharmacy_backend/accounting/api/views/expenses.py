# PATH: accounting/api/views/expenses.py

"""
PATH: accounting/api/views/expenses.py

EXPENSES API (PHASE 5 HARDENED)

GET  /api/accounting/expenses/
    - Requires permission: accounting.view_ledgerentry
    - Read-only access (audit-safe)

POST /api/accounting/expenses/
    - Requires permission: accounting.add_expense
    - Creates expense + posts to ledger (atomic)

Phase 5 Notes:
- No is_staff checks
- Group/user permissions honored via has_perm
- Tenant safety: best-effort scoping hook; superuser override
"""

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from rest_framework.generics import GenericAPIView

from drf_spectacular.utils import extend_schema

from accounting.models.expense import Expense
from accounting.api.serializers.expenses import (
    ExpenseSerializer,
    ExpenseCreateSerializer,
)
from accounting.services.expense_service import (
    create_expense_and_post,
    ExpensePostingError,
    ExpensePermissionError,
)
from accounting.services.account_resolver import get_active_chart


EXPENSE_VIEW_PERMISSION = "accounting.view_ledgerentry"
EXPENSE_POST_PERMISSION = "accounting.add_expense"


def _scope_expenses_queryset(request, qs):
    """
    Tenant safety hook.

    If your Expense model has a chart/business foreign key, filter it here.
    We avoid assuming field names to prevent breaking your project.

    Current behavior:
    - Superuser sees all
    - Otherwise, if a 'chart' FK exists, scope to active chart
    - Else, return qs as-is (still permission-gated)
    """
    user = getattr(request, "user", None)
    if user and getattr(user, "is_superuser", False):
        return qs

    chart = None
    try:
        chart = get_active_chart()
    except Exception:
        chart = None

    if chart is None:
        return qs

    # Best-effort: only apply if model has a "chart" field
    try:
        Expense._meta.get_field("chart")
        return qs.filter(chart=chart)
    except Exception:
        return qs


class ExpenseListCreateView(GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ExpenseCreateSerializer

    @extend_schema(
        tags=["accounting"],
        responses=ExpenseSerializer(many=True),
    )
    def get(self, request, *args, **kwargs):
        # ✅ Permission hardening (matrix: viewing financial data)
        if not request.user.has_perm(EXPENSE_VIEW_PERMISSION):
            return Response(
                {"detail": "You do not have permission to view expenses."},
                status=status.HTTP_403_FORBIDDEN,
            )

        qs = Expense.objects.select_related(
            "expense_account",
            "payment_account",
            "posted_journal_entry",
        ).order_by("-expense_date", "-created_at")

        qs = _scope_expenses_queryset(request, qs)

        return Response(ExpenseSerializer(qs, many=True).data, status=status.HTTP_200_OK)

    @extend_schema(
        tags=["accounting"],
        request=ExpenseCreateSerializer,
        responses={201: ExpenseSerializer, 400: dict, 403: dict},
    )
    def post(self, request, *args, **kwargs):
        # ✅ Permission hardening (matrix: Expense Post -> accounting.add_expense)
        if not request.user.has_perm(EXPENSE_POST_PERMISSION):
            return Response(
                {"detail": "You do not have permission to post expenses."},
                status=status.HTTP_403_FORBIDDEN,
            )

        s = self.get_serializer(data=request.data)
        s.is_valid(raise_exception=True)
        data = s.validated_data

        try:
            expense = create_expense_and_post(
                user=request.user,
                expense_date=data["expense_date"],
                amount=data["amount"],
                expense_account_code=data["expense_account_code"],
                payment_method=data["payment_method"],
                payable_account_code=data.get("payable_account_code"),
                vendor=data.get("vendor", ""),
                narration=data.get("narration", ""),
            )
        except ExpensePermissionError as exc:
            # Service-level permission errors still respected (defense-in-depth)
            return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
        except ExpensePostingError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(ExpenseSerializer(expense).data, status=status.HTTP_201_CREATED)
