# accounting/services/pos_accounting_service.py
 
"""
POS → ACCOUNTING ORCHESTRATOR

This service is the ONLY bridge between the POS domain
and the accounting engine.

Responsibilities:
- Validate POS sale readiness
- Enforce idempotency (no double posting)
- Delegate accounting intent to posting rules
- Mark sale as accounted ONLY after successful posting

NO accounting math lives here.
NO journal / ledger writes live here.
"""

from django.db import transaction

from accounting.services.exceptions import AccountingServiceError
from accounting.services.posting_rules import post_pos_sale


@transaction.atomic
def post_sale_to_accounting(sale):
    """
    Entry point for posting a POS sale into accounting.

    This function MUST be called exactly once per completed sale.
    It is safe against partial failure and double-posting.
    """

    # --------------------------------------------------
    # BASIC VALIDATION
    # --------------------------------------------------
    if sale is None:
        raise AccountingServiceError("Sale cannot be None")

    if not hasattr(sale, "id"):
        raise AccountingServiceError("Invalid sale object")

    # --------------------------------------------------
    # BUSINESS STATE VALIDATION
    # --------------------------------------------------
    if getattr(sale, "is_cancelled", False):
        raise AccountingServiceError(
            f"Sale {sale.id} is cancelled and cannot be posted"
        )

    if not getattr(sale, "is_completed", True):
        raise AccountingServiceError(
            f"Sale {sale.id} is not completed and cannot be posted"
        )

    # --------------------------------------------------
    # IDEMPOTENCY GUARARD (NON-NEGOTIABLE)
    # --------------------------------------------------
    if getattr(sale, "is_accounted", False):
        raise AccountingServiceError(
            f"Sale {sale.id} has already been posted to accounting"
        )

    # --------------------------------------------------
    # DELEGATE TO POSTING RULES
    # --------------------------------------------------
    post_pos_sale(sale)

    # --------------------------------------------------
    # MARK SALE AS ACCOUNTED (ATOMIC)
    # --------------------------------------------------
    sale.is_accounted = True
    sale.save(update_fields=["is_accounted"])
