# products/services/stock_intake.py

"""
STOCK INTAKE / PURCHASE RECEIPT (APPLICATION SERVICE)

Purpose:
- Intake stock ONLY via a purchase-style receipt (delivery-based).
- Capture immutable unit cost (cost basis) for valuation + COGS.
- Produce a matching StockMovement(RECEIPT) ledger record.
- Keep everything atomic and audit-safe.

HOTSPRINT UPGRADE (PRICING + MARKUP READY):
- Supports optional markup policy to auto-calculate selling price.
"""

from __future__ import annotations

import uuid
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction, IntegrityError
from django.core.exceptions import ValidationError

from products.models import StockBatch, StockMovement


TWOPLACES = Decimal("0.01")


def _money(v) -> Decimal:
    if v is None or v == "":
        return Decimal("0.00")
    return Decimal(str(v)).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def _resolve_store_id(*, product, store=None):
    store_id = getattr(store, "id", store) if store is not None else getattr(product, "store_id", None)
    if not store_id:
        raise ValidationError("store is required (either pass store or ensure product.store is set)")
    return store_id


def _calc_selling_price(*, unit_cost: Decimal, markup_percent=None, markup_amount=None) -> Decimal | None:
    if markup_percent is not None and markup_amount is not None:
        raise ValidationError("Provide either markup_percent or markup_amount, not both")

    if markup_percent is None and markup_amount is None:
        return None

    if markup_percent is not None:
        mp = _money(markup_percent)
        if mp < Decimal("0.00"):
            raise ValidationError("markup_percent must be >= 0")
        return (unit_cost * (Decimal("1.00") + (mp / Decimal("100.00")))).quantize(TWOPLACES, rounding=ROUND_HALF_UP)

    ma = _money(markup_amount)
    if ma < Decimal("0.00"):
        raise ValidationError("markup_amount must be >= 0")
    return (unit_cost + ma).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


@transaction.atomic
def intake_stock(
    *,
    product,
    quantity_received: int,
    unit_cost,
    expiry_date,
    batch_number: str | None = None,
    user=None,
    store=None,
    markup_percent=None,
    markup_amount=None,
    update_product_price: bool = False,
):
    if not product:
        raise ValidationError("Product is required")

    store_id = _resolve_store_id(product=product, store=store)

    if quantity_received is None or int(quantity_received) <= 0:
        raise ValidationError("quantity_received must be greater than zero")

    if not expiry_date:
        raise ValidationError("expiry_date is required")

    unit_cost_dec = _money(unit_cost)
    if unit_cost_dec <= Decimal("0.00"):
        raise ValidationError("unit_cost must be greater than zero")

    bn = (batch_number or "").strip()
    if not bn:
        bn = f"INTAKE-{uuid.uuid4().hex[:10].upper()}"

    selling_price = _calc_selling_price(
        unit_cost=unit_cost_dec,
        markup_percent=markup_percent,
        markup_amount=markup_amount,
    )

    if update_product_price and selling_price is None:
        raise ValidationError("update_product_price=True requires markup_percent or markup_amount")

    try:
        batch = StockBatch.objects.create(
            store_id=store_id,
            product=product,
            batch_number=bn,
            expiry_date=expiry_date,
            quantity_received=int(quantity_received),
            quantity_remaining=int(quantity_received),
            unit_cost=unit_cost_dec,
        )
    except IntegrityError as exc:
        raise ValidationError(
            "StockBatch creation failed: batch_number already exists for this store+product. "
            "Ensure each delivery batch_number is unique per store per product."
        ) from exc

    StockMovement.objects.create(
        product=product,
        batch=batch,
        movement_type=StockMovement.MovementType.IN,
        reason=StockMovement.Reason.RECEIPT,
        quantity=int(quantity_received),
        unit_cost_snapshot=unit_cost_dec,
        performed_by=user,
    )

    if update_product_price:
        if selling_price <= Decimal("0.00"):
            raise ValidationError("Calculated selling price must be > 0")
        product.unit_price = selling_price
        product.save(update_fields=["unit_price"])

    return batch
