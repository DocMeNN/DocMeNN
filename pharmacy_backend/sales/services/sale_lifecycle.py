"""
SALE LIFECYCLE DOMAIN RULES

This module defines the ONLY allowed lifecycle transitions
for Sale entities.

DESIGN PRINCIPLES:
- No database writes
- No stock mutation
- No side effects
- Single source of truth
"""

from sales.models import Sale

# ============================================================
# DOMAIN ERRORS
# ============================================================


class SaleLifecycleError(Exception):
    pass


class InvalidSaleTransitionError(SaleLifecycleError):
    pass


# ============================================================
# STATE DEFINITIONS
# ============================================================

TERMINAL_STATES = {
    Sale.STATUS_REFUNDED,
}

ALLOWED_TRANSITIONS = {
    Sale.STATUS_COMPLETED: {
        Sale.STATUS_REFUNDED,
    },
}


# ============================================================
# DOMAIN RULES
# ============================================================


def can_transition(*, from_status: str, to_status: str) -> bool:
    if from_status in TERMINAL_STATES:
        return False

    return to_status in ALLOWED_TRANSITIONS.get(from_status, set())


def validate_transition(*, sale: Sale, target_status: str):
    if not can_transition(
        from_status=sale.status,
        to_status=target_status,
    ):
        raise InvalidSaleTransitionError(
            f"Sale {sale.id} cannot transition from "
            f"'{sale.status}' to '{target_status}'"
        )
