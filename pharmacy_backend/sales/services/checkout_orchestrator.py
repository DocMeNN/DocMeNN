# sales/services/checkout_orchestrator.py

"""
CHECKOUT ORCHESTRATOR (APPLICATION SERVICE)

Purpose:
- Finalize an active cart into a completed Sale (atomic, auditable).
- Validate + deduct stock using FEFO/FIFO rules within the cart's store context.
- Post accounting entry after sale is finalized.

Hard rules:
- Quantities are integer units (StockMovement.quantity is integer).
- Money values are computed server-side; frontend never calculates totals.

SPLIT PAYMENT:
- If payment_allocations is provided:
  - sum(amount) must equal sale.total_amount (2dp exact)
  - sale.payment_method is set to "split"
  - immutable SalePaymentAllocation rows are created

Notes:
- We keep the whole checkout inside one DB transaction:
  stock movements + sale rows + ledger posting succeed together or rollback together.
- Period lock is enforced at the accounting choke-point (journal entry service).
  We may optionally pre-check in posting, but the engine remains final authority.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from sales.models import Sale, SaleItem, SalePaymentAllocation
from products.models.stock_batch import StockBatch
from products.services.stock_fifo import deduct_stock_fifo, InsufficientStockError

from accounting.services.posting import post_sale_to_ledger
from accounting.services.exceptions import (
    JournalEntryCreationError,
    IdempotencyError,
    AccountResolutionError,
)

TWOPLACES = Decimal("0.01")


def _money(v) -> Decimal:
    if v is None or v == "":
        return Decimal("0.00")
    return Decimal(str(v)).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def _to_int_qty(value) -> int:
    if value is None or value == "":
        return 0

    if isinstance(value, bool):
        raise ValueError("quantity must be a whole integer unit")

    if isinstance(value, int):
        return value

    if isinstance(value, str):
        s = value.strip()
        if s.isdigit():
            return int(s)

    raise ValueError("quantity must be a whole integer unit")


def _normalize_payment_method(method: str | None) -> str:
    m = (method or "cash").strip().lower()
    return m or "cash"


def _available_stock_for_store(*, product, store_id, today) -> int:
    """
    Primary: store_id match
    Transitional fallback: NULL-store batches if store-specific batches don't exist.
    """
    base = StockBatch.objects.filter(
        product=product,
        is_active=True,
        expiry_date__gte=today,
        quantity_remaining__gt=0,
    )

    store_qs = base.filter(store_id=store_id)
    if store_qs.exists():
        total = store_qs.aggregate(total=Sum("quantity_remaining")).get("total")
        return int(total or 0)

    null_store_qs = base.filter(store__isnull=True)
    if null_store_qs.exists():
        total = null_store_qs.aggregate(total=Sum("quantity_remaining")).get("total")
        return int(total or 0)

    return 0


def _safe_setattr(obj, field_name: str, value) -> bool:
    if hasattr(obj, field_name):
        setattr(obj, field_name, value)
        return True
    return False


def _validate_and_normalize_allocations(allocations) -> list[dict]:
    """
    allocations: list of dicts: {method, amount, reference?, note?}
    Returns normalized list with Decimal 2dp amounts.
    """
    if not allocations:
        return []

    out = []
    for idx, a in enumerate(allocations):
        method = str(a.get("method", "")).strip().lower()
        if method not in {"cash", "bank", "pos", "transfer", "credit"}:
            raise ValueError(f"Invalid payment allocation method at index {idx}: {method}")

        amt = _money(a.get("amount", None))
        if amt <= Decimal("0.00"):
            raise ValueError(f"Invalid payment allocation amount at index {idx}: {amt}")

        out.append(
            {
                "method": method,
                "amount": amt,
                "reference": str(a.get("reference", "") or "").strip(),
                "note": str(a.get("note", "") or "").strip(),
            }
        )

    return out


class CheckoutError(Exception):
    """Base checkout exception"""


class EmptyCartError(CheckoutError):
    pass


class StockValidationError(CheckoutError):
    pass


class AccountingPostingError(CheckoutError):
    pass


@transaction.atomic
def checkout_cart(*, user, cart, payment_method: str | None, payment_allocations=None) -> Sale:
    # Lock cart row early if possible (prevents racey double-checkout clicks).
    try:
        cart = cart.__class__.objects.select_for_update().get(pk=cart.pk)
    except Exception:
        # If cart is not a model instance with manager access, proceed (best-effort).
        pass

    if not getattr(cart, "is_active", True):
        raise CheckoutError("Cart is not active")

    if not cart.items.exists():
        raise EmptyCartError("Cart is empty")

    store_id = getattr(cart, "store_id", None)
    store_obj = getattr(cart, "store", None)
    if not store_id:
        raise CheckoutError("Cart.store is required for checkout (multi-store scope)")

    cart_items = list(cart.items.select_related("product").select_for_update())

    for item in cart_items:
        p_store_id = getattr(item.product, "store_id", None)
        if p_store_id and p_store_id != store_id:
            raise CheckoutError(
                f"Cart store mismatch: product '{item.product.name}' belongs to a different store."
            )

    today = timezone.localdate()

    # Stock availability validation first (fast fail before writing anything heavy).
    for item in cart_items:
        try:
            requested_qty = _to_int_qty(getattr(item, "quantity", 0))
        except ValueError:
            raise StockValidationError(
                f"Invalid quantity for {getattr(item.product, 'name', 'product')}. Quantity must be a whole number."
            )

        if requested_qty <= 0:
            raise StockValidationError(
                f"Invalid quantity for {getattr(item.product, 'name', 'product')}. Quantity must be at least 1."
            )

        available_qty = _available_stock_for_store(product=item.product, store_id=store_id, today=today)
        if available_qty < requested_qty:
            raise StockValidationError(
                f"Insufficient stock for {item.product.name}. "
                f"Available: {available_qty}, Requested: {requested_qty}"
            )

    normalized_allocs = _validate_and_normalize_allocations(payment_allocations)

    pm = _normalize_payment_method(payment_method)
    if normalized_allocs:
        pm = "split"

    # Pull tax/discount from cart (server-side truth) if present.
    cart_tax = _money(getattr(cart, "tax_amount", None))
    cart_discount = _money(getattr(cart, "discount_amount", None))

    sale_create_kwargs = dict(
        user=user,
        payment_method=pm,
        status=Sale.STATUS_DRAFT,
        subtotal_amount=Decimal("0.00"),
        total_amount=Decimal("0.00"),
    )

    # Optional fields (safe, schema-flexible).
    _safe_setattr(type("X", (), {})(), "noop", None)  # no-op to keep helper “used” in static analyzers

    if hasattr(Sale, "store_id"):
        sale_create_kwargs["store_id"] = store_id
    elif hasattr(Sale, "store"):
        sale_create_kwargs["store"] = store_obj

    # If Sale has tax/discount fields, set them from cart.
    if hasattr(Sale, "tax_amount"):
        sale_create_kwargs["tax_amount"] = cart_tax
    if hasattr(Sale, "discount_amount"):
        sale_create_kwargs["discount_amount"] = cart_discount

    # If cart captures customer_name, carry it forward if Sale supports it.
    if hasattr(Sale, "customer_name") and hasattr(cart, "customer_name"):
        sale_create_kwargs["customer_name"] = str(getattr(cart, "customer_name", "") or "").strip()

    sale = Sale.objects.create(**sale_create_kwargs)

    subtotal = Decimal("0.00")
    sale_cogs_total = Decimal("0.00")

    try:
        for item in cart_items:
            qty_int = _to_int_qty(item.quantity)

            # Prefer item.unit_price if present; otherwise fall back to product selling price.
            unit_price = _money(getattr(item, "unit_price", None))
            if unit_price == Decimal("0.00"):
                unit_price = _money(getattr(item.product, "selling_price", None))

            if unit_price <= Decimal("0.00"):
                raise StockValidationError(
                    f"Invalid unit price for {getattr(item.product, 'name', 'product')}. Must be > 0."
                )

            sale_item = SaleItem.objects.create(
                sale=sale,
                product=item.product,
                quantity=qty_int,
                unit_price=unit_price,
            )

            fifo_movements = deduct_stock_fifo(
                product=item.product,
                quantity=qty_int,
                user=user,
                sale=sale,
                store=store_id,
            )

            line_cogs = Decimal("0.00")
            for mv in fifo_movements or []:
                mv_qty = int(getattr(mv, "quantity", 0) or 0)
                raw_uc = getattr(mv, "unit_cost_snapshot", None)
                if raw_uc in (None, "", "null"):
                    raise StockValidationError(
                        "Missing unit_cost_snapshot on FIFO SALE movement. "
                        "Backfill StockBatch.unit_cost for affected batches before selling."
                    )
                mv_unit_cost = _money(raw_uc)
                if mv_unit_cost <= Decimal("0.00"):
                    raise StockValidationError(
                        "Invalid unit_cost_snapshot on FIFO SALE movement (must be > 0). "
                        "Backfill StockBatch.unit_cost and regenerate cost snapshots."
                    )
                line_cogs += (mv_unit_cost * Decimal(mv_qty))

            sale_cogs_total += _money(line_cogs)

            line_revenue = _money(unit_price * Decimal(qty_int))
            line_gross_profit = _money(line_revenue - line_cogs)

            dirty_fields = []

            avg_unit_cost = Decimal("0.00")
            if qty_int:
                avg_unit_cost = (line_cogs / Decimal(qty_int)).quantize(TWOPLACES, rounding=ROUND_HALF_UP)

            if _safe_setattr(sale_item, "unit_cost", avg_unit_cost):
                dirty_fields.append("unit_cost")
            if _safe_setattr(sale_item, "cost_amount", _money(line_cogs)):
                dirty_fields.append("cost_amount")
            if _safe_setattr(sale_item, "gross_profit_amount", _money(line_gross_profit)):
                dirty_fields.append("gross_profit_amount")
            if _safe_setattr(sale_item, "line_total_amount", _money(line_revenue)):
                dirty_fields.append("line_total_amount")

            if dirty_fields:
                sale_item.save(update_fields=dirty_fields)

            subtotal += _money(line_revenue)

    except InsufficientStockError as exc:
        raise StockValidationError(str(exc)) from exc
    except ValueError as exc:
        raise StockValidationError(str(exc)) from exc

    # Re-read tax/discount from sale if the model uses signals/defaults; otherwise keep cart-derived values.
    tax = _money(getattr(sale, "tax_amount", cart_tax))
    discount = _money(getattr(sale, "discount_amount", cart_discount))

    subtotal = _money(subtotal)
    total = _money(subtotal + tax - discount)

    sale.subtotal_amount = subtotal
    sale.total_amount = total
    sale.completed_at = timezone.now()
    sale.status = Sale.STATUS_COMPLETED

    sale_gross_profit = _money(subtotal - sale_cogs_total)
    extra_update_fields = []

    if _safe_setattr(sale, "cogs_amount", _money(sale_cogs_total)):
        extra_update_fields.append("cogs_amount")
    if _safe_setattr(sale, "gross_profit_amount", _money(sale_gross_profit)):
        extra_update_fields.append("gross_profit_amount")

    # Ensure tax/discount persisted if these fields exist.
    if hasattr(sale, "tax_amount"):
        sale.tax_amount = tax
        extra_update_fields.append("tax_amount")
    if hasattr(sale, "discount_amount"):
        sale.discount_amount = discount
        extra_update_fields.append("discount_amount")

    sale.save(
        update_fields=["subtotal_amount", "total_amount", "completed_at", "status"] + extra_update_fields
    )

    # SPLIT PAYMENT: enforce sum(amount) == total, then create allocations
    if normalized_allocs:
        alloc_total = _money(sum((a["amount"] for a in normalized_allocs), Decimal("0.00")))
        if alloc_total != total:
            raise CheckoutError(
                f"Split payment mismatch: allocations sum({alloc_total}) != sale total({total})."
            )

        # Ensure payment_method is locked to split
        if sale.payment_method != "split":
            sale.payment_method = "split"
            sale.save(update_fields=["payment_method"])

        for a in normalized_allocs:
            SalePaymentAllocation.objects.create(
                sale=sale,
                method=a["method"],
                amount=a["amount"],
                reference=a["reference"],
                note=a["note"],
            )

    # Post to ledger (engine enforces period lock + idempotency).
    try:
        post_sale_to_ledger(sale=sale)
    except (JournalEntryCreationError, IdempotencyError, AccountResolutionError) as exc:
        raise AccountingPostingError(str(exc)) from exc
    except Exception as exc:
        raise AccountingPostingError(f"Ledger posting failed: {exc}") from exc

    cart.items.all().delete()
    cart.is_active = False
    cart.save(update_fields=["is_active"])

    return sale
