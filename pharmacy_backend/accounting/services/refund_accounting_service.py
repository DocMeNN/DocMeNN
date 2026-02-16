# refund_accounting_service.py

"""
REFUND → ACCOUNTING ORCHESTRATOR

This service handles posting of POS refunds into accounting.

Responsibilities:
- Enforce idempotency (refund posted once)
- Validate refund integrity
- Delegate accounting logic to posting rules

NO accounting math lives here.
NO ledger writes live here.
"""

from accounting.services.posting_rules_refund import post_pos_refund
from accounting.services.exceptions import AccountingServiceError


def post_refund_to_accounting(refund):
    """
    Entry point for posting a POS refund into accounting.
    """

    if refund is None:
        raise AccountingServiceError("Refund cannot be None")

    if getattr(refund, "is_accounted", False):
        raise AccountingServiceError(
            f"Refund {refund.id} has already been posted to accounting"
        )

    # --------------------------------------------------
    # Delegate accounting logic
    # --------------------------------------------------
    post_pos_refund(refund)

    # --------------------------------------------------
    # Mark refund as accounted (idempotency)
    # --------------------------------------------------
    refund.is_accounted = True
    refund.save(update_fields=["is_accounted"])
