"""
======================================================
PATH: backend/events/handlers.py
======================================================

DOMAIN EVENT HANDLERS

Handlers connect domains together.

Examples:
- OrderCompleted → analytics
- StockDeducted → inventory projections
- GoodsReceived → supplier metrics
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from backend.events.event_bus import register
from backend.events.domain.inventory_events import (
    StockAdjusted,
    StockDeducted,
    StockRestored,
)
from backend.events.domain.purchase_events import GoodsReceived
from backend.events.domain.order_events import OrderCompleted
from backend.events.domain.refund_events import RefundCompleted

logger = logging.getLogger(__name__)


def _payload(event: Any) -> Dict[str, Any]:
    """
    Support both:
    - real event objects
    - payload dicts (from the outbox)
    """
    if isinstance(event, dict):
        return event
    return event.to_dict()


def handle_goods_received(event: GoodsReceived | Dict[str, Any]):

    data = _payload(event)

    logger.info(
        "Goods received",
        extra={
            "invoice_id": data.get("invoice_id"),
            "supplier_id": data.get("supplier_id"),
            "total_amount": str(data.get("total_amount")),
        },
    )


def handle_stock_deducted(event: StockDeducted | Dict[str, Any]):

    data = _payload(event)

    logger.info(
        "Stock deducted",
        extra={
            "product_id": data.get("product_id"),
            "batch_id": data.get("batch_id"),
            "quantity": data.get("quantity"),
        },
    )


def handle_stock_restored(event: StockRestored | Dict[str, Any]):

    data = _payload(event)

    logger.info(
        "Stock restored",
        extra={
            "product_id": data.get("product_id"),
            "batch_id": data.get("batch_id"),
            "quantity": data.get("quantity"),
        },
    )


def handle_stock_adjusted(event: StockAdjusted | Dict[str, Any]):

    data = _payload(event)

    logger.info(
        "Stock adjusted",
        extra={
            "product_id": data.get("product_id"),
            "batch_id": data.get("batch_id"),
            "quantity_delta": data.get("quantity_delta"),
        },
    )


def handle_order_completed(event: OrderCompleted | Dict[str, Any]):

    data = _payload(event)

    logger.info(
        "Order completed",
        extra={
            "sale_id": data.get("sale_id"),
            "user_id": data.get("user_id"),
            "total_amount": str(data.get("total_amount")),
        },
    )


def handle_refund_completed(event: RefundCompleted | Dict[str, Any]):

    data = _payload(event)

    logger.info(
        "Refund completed",
        extra={
            "sale_id": data.get("sale_id"),
            "refund_id": data.get("refund_id"),
            "total_amount": str(data.get("total_amount")),
        },
    )


# -----------------------------------------------------
# Register handlers
# -----------------------------------------------------

register(GoodsReceived, handle_goods_received)
register(StockDeducted, handle_stock_deducted)
register(StockRestored, handle_stock_restored)
register(StockAdjusted, handle_stock_adjusted)
register(OrderCompleted, handle_order_completed)
register(RefundCompleted, handle_refund_completed)