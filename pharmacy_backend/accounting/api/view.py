# PATH: accounting/api/view.py

"""
PATH: accounting/api/view.py

ACCOUNTING API VIEWSETS (READ-ONLY / AUDIT SAFE)

Goal (Phase 5 hardening):
- Keep audit endpoints strictly read-only
- Permission-gate access via Django permissions (no role hardcoding)
- Add lightweight filtering WITHOUT django-filter dependency:
    /api/accounting/ledger-entries/?journal_entry=30
    /api/accounting/ledger-entries/?account=28
    /api/accounting/ledger-entries/?journal_entry=30&account=28
- Basic ordering via ?ordering=created_at or ?ordering=-created_at

Security rules:
- JournalEntry list requires accounting.view_journalentry
- LedgerEntry list requires accounting.view_ledgerentry

Model guarantee:
- LedgerEntry.clean() already enforces journal_entry.is_posted == True,
  so there is no LedgerEntry.is_posted field and no extra filtering is required.
"""

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import ReadOnlyModelViewSet

from accounting.api.serializers import JournalEntrySerializer, LedgerEntrySerializer
from accounting.models.journal import JournalEntry
from accounting.models.ledger import LedgerEntry


@extend_schema(tags=["accounting"])
class JournalEntryViewSet(ReadOnlyModelViewSet):
    """
    Read-only access to journal entries (audit-safe).
    """

    permission_classes = [IsAuthenticated]
    serializer_class = JournalEntrySerializer
    http_method_names = ["get", "head", "options"]

    queryset = JournalEntry.objects.filter(is_posted=True).order_by("-posted_at")

    def get_queryset(self):
        if not self.request.user.has_perm("accounting.view_journalentry"):
            raise PermissionDenied(
                "You do not have permission to view journal entries."
            )
        return super().get_queryset()


@extend_schema(
    tags=["accounting"],
    parameters=[
        OpenApiParameter(
            name="journal_entry",
            type=int,
            required=False,
            description="Filter ledger entries by JournalEntry id (e.g. 30).",
        ),
        OpenApiParameter(
            name="account",
            type=int,
            required=False,
            description="Filter ledger entries by Account id (e.g. 28).",
        ),
        OpenApiParameter(
            name="ordering",
            type=str,
            required=False,
            description="Order results (allowed: created_at, -created_at). Default: -created_at",
        ),
    ],
)
class LedgerEntryViewSet(ReadOnlyModelViewSet):
    """
    Read-only access to ledger entries (append-only, audit-safe).

    Filtering (no extra deps):
    - ?journal_entry=<id>
    - ?account=<id>

    Ordering:
    - ?ordering=created_at
    - ?ordering=-created_at
    """

    permission_classes = [IsAuthenticated]
    serializer_class = LedgerEntrySerializer
    http_method_names = ["get", "head", "options"]

    queryset = LedgerEntry.objects.select_related("journal_entry", "account")

    def get_queryset(self):
        if not self.request.user.has_perm("accounting.view_ledgerentry"):
            raise PermissionDenied("You do not have permission to view ledger entries.")

        qs = super().get_queryset()

        qp = getattr(self.request, "query_params", None)
        if not qp:
            return qs.order_by("-created_at")

        journal_entry = qp.get("journal_entry")
        account = qp.get("account")

        if journal_entry:
            try:
                qs = qs.filter(journal_entry_id=int(journal_entry))
            except (TypeError, ValueError):
                pass

        if account:
            try:
                qs = qs.filter(account_id=int(account))
            except (TypeError, ValueError):
                pass

        ordering = (qp.get("ordering") or "-created_at").strip()
        if ordering not in ("created_at", "-created_at"):
            ordering = "-created_at"

        return qs.order_by(ordering)
