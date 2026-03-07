# products/services/accounting_cogs_bridge.py

"""
Bridge between Inventory (FIFO) and Accounting (COGS).

Responsibilities
- Receive inventory cost from FIFO
- Build accounting postings
- Send to journal entry engine
"""

from decimal import Decimal

from accounting.services.journal_entry_service import create_journal_entry
from accounting.services.posting_rules_cogs import build_cogs_posting


def post_cogs_for_sale(
    *,
    cost_amount: Decimal,
    reference_id: str,
    description: str,
):
    """
    Post COGS journal entry for a completed sale.
    """

    postings = build_cogs_posting(cost_amount)

    return create_journal_entry(
        description=description,
        postings=postings,
        reference_type="COGS",
        reference_id=reference_id,
    )