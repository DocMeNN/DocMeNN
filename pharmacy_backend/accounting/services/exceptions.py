# accounting/services/exceptions.py

"""
ACCOUNTING SERVICE ERRORS

Centralized domain errors for accounting services.
"""


class AccountingServiceError(Exception):
    """Base exception for all accounting service failures."""


class PostingRuleError(AccountingServiceError):
    """Raised when a posting rule cannot be applied."""


class AccountResolutionError(AccountingServiceError):
    """Raised when an expected account cannot be resolved."""


class JournalEntryCreationError(AccountingServiceError):
    """Raised when a journal entry cannot be created."""


class IdempotencyError(AccountingServiceError):
    """Raised on duplicate or retried accounting events."""
