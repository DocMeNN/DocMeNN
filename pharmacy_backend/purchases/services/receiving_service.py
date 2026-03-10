"""
======================================================
PATH: purchases/services/receiving_service.py
======================================================
PURCHASE RECEIVING SERVICE
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.utils import timezone

from accounting.models.account import Account
from accounting.models.journal import JournalEntry
from accounting.services.account_resolver import (
    get_accounts_payable_account,
    get_active_chart,
    get_inventory_account,
)
from accounting.services.exceptions import (
    AccountResolutionError,
    IdempotencyError,
    JournalEntryCreationError,
)
from accounting.services.posting import post_purchase_receipt_to_ledger
from products.models.stock_batch import StockBatch
from products.services.inventory import intake_stock
from purchases.models import PurchaseInvoice

from backend.events.event_bus import publish
from backend.events.domain.purchase_events import GoodsReceived


class PurchaseReceivingError(ValueError):
    pass


TWOPLACES = Decimal("0.01")


def _money(v) -> Decimal:
    return Decimal(str(v or "0.00")).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def _resolve_account_by_code(*, code: str) -> Account:
    chart = get_active_chart()
    code = (code or "").strip()
    if not code:
        raise PurchaseReceivingError("Account code is required")

    try:
        return Account.objects.get(chart=chart, code=code, is_active=True)
    except Account.DoesNotExist as exc:
        raise AccountResolutionError(
            f"Account with code={code} not found in active chart ({getattr(chart, 'name', 'ACTIVE_CHART')})."
        ) from exc
    except Account.MultipleObjectsReturned as exc:
        raise AccountResolutionError(
            f"Multiple active accounts found with code={code} in active chart ({getattr(chart, 'name', 'ACTIVE_CHART')}). "
            "Account codes must be unique per chart."
        ) from exc


def _resolve_inventory_and_payable_accounts(
    *,
    inventory_account_code: str | None,
    payable_account_code: str | None,
):

    inv_code = (inventory_account_code or "").strip()
    ap_code = (payable_account_code or "").strip()

    inventory_account = (
        _resolve_account_by_code(code=inv_code) if inv_code else get_inventory_account()
    )

    payable_account = (
        _resolve_account_by_code(code=ap_code)
        if ap_code
        else get_accounts_payable_account()
    )

    return inventory_account, payable_account


def _get_existing_purchase_receipt_journal_entry(*, invoice_id: str) -> JournalEntry:

    ref = f"PURCHASE_RECEIPT:{str(invoice_id).strip()}"

    try:
        return JournalEntry.objects.get(reference=ref)
    except JournalEntry.DoesNotExist as exc:
        raise PurchaseReceivingError(
            "Ledger posting already exists (idempotency), but the journal entry could not be found by reference. "
            f"Expected reference={ref}."
        ) from exc


def _batch_conflict_guard(
    *, product, batch_number: str, expiry_date, qty: int, unit_cost: Decimal
):

    existing = StockBatch.objects.filter(
        product=product,
        batch_number=batch_number
    ).first()

    if not existing:
        return

    ex_exp = getattr(existing, "expiry_date", None)
    ex_qty = int(getattr(existing, "quantity_received", 0) or 0)
    ex_cost_raw = getattr(existing, "unit_cost", None)

    try:
        ex_cost = _money(ex_cost_raw)
    except Exception:
        ex_cost = None

    if ex_exp and ex_exp != expiry_date:
        raise PurchaseReceivingError(
            f"Batch conflict for product={getattr(product, 'id', product)} batch_number={batch_number!r}: "
            f"existing expiry_date={ex_exp} != invoice expiry_date={expiry_date}."
        )

    if ex_qty and ex_qty != int(qty):
        raise PurchaseReceivingError(
            f"Batch conflict for product={getattr(product, 'id', product)} batch_number={batch_number!r}: "
            f"existing quantity_received={ex_qty} != invoice quantity={qty}."
        )

    if ex_cost is not None and ex_cost != _money(unit_cost):
        raise PurchaseReceivingError(
            f"Batch conflict for product={getattr(product, 'id', product)} batch_number={batch_number!r}: "
            f"existing unit_cost={ex_cost} != invoice unit_cost={_money(unit_cost)}."
        )


@transaction.atomic
def receive_purchase_invoice(
    *,
    invoice_id,
    inventory_account_code: str | None,
    payable_account_code: str | None,
):

    try:
        invoice = (
            PurchaseInvoice.objects
            .select_for_update()
            .prefetch_related("items", "items__product")
            .get(id=invoice_id)
        )
    except PurchaseInvoice.DoesNotExist as exc:
        raise PurchaseReceivingError("Purchase invoice not found") from exc

    if invoice.status == PurchaseInvoice.STATUS_RECEIVED:

        try:
            je = _get_existing_purchase_receipt_journal_entry(
                invoice_id=str(invoice.id)
            )
            je_id = str(je.id)
        except Exception:
            je_id = ""

        return {
            "invoice_id": str(invoice.id),
            "status": invoice.status,
            "subtotal_amount": str(getattr(invoice, "subtotal_amount", "") or ""),
            "total_amount": str(getattr(invoice, "total_amount", "") or ""),
            "journal_entry_id": je_id,
        }

    if invoice.status != PurchaseInvoice.STATUS_DRAFT:
        raise PurchaseReceivingError("Only DRAFT invoices can be received")

    items = list(invoice.items.all())

    if not items:
        raise PurchaseReceivingError("Invoice has no items")

    inventory_account, payable_account = _resolve_inventory_and_payable_accounts(
        inventory_account_code=inventory_account_code,
        payable_account_code=payable_account_code,
    )

    subtotal = Decimal("0.00")

    for it in items:

        if it.quantity <= 0:
            raise PurchaseReceivingError("Item quantity must be > 0")

        if it.unit_cost in (None, "", "null"):
            raise PurchaseReceivingError("Item unit_cost is required")

        if Decimal(str(it.unit_cost)) < Decimal("0.00"):
            raise PurchaseReceivingError("Item unit_cost cannot be negative")

        if not (it.batch_number or "").strip():
            raise PurchaseReceivingError(
                "Item batch_number is required (supplier delivery batch reference)"
            )

        if not it.expiry_date:
            raise PurchaseReceivingError("Item expiry_date is required")

        subtotal += it.line_total

    subtotal = _money(subtotal)
    total = subtotal

    received_date = timezone.localdate()

    try:
        je = post_purchase_receipt_to_ledger(
            invoice_id=str(invoice.id),
            invoice_number=invoice.invoice_number,
            received_date=received_date,
            inventory_account=inventory_account,
            payable_account=payable_account,
            amount=total,
        )
    except IdempotencyError:
        je = _get_existing_purchase_receipt_journal_entry(
            invoice_id=str(invoice.id)
        )
    except JournalEntryCreationError as exc:
        raise PurchaseReceivingError(str(exc)) from exc
    except Exception as exc:
        raise PurchaseReceivingError(
            f"Failed to post purchase receipt: {exc}"
        ) from exc

    performer = getattr(invoice, "created_by", None)

    try:
        for it in items:

            product = it.product
            batch_number = (it.batch_number or "").strip()
            expiry_date = it.expiry_date
            qty = int(it.quantity)
            unit_cost = _money(it.unit_cost)

            _batch_conflict_guard(
                product=product,
                batch_number=batch_number,
                expiry_date=expiry_date,
                qty=qty,
                unit_cost=unit_cost,
            )

            intake_stock(
                product=product,
                batch_number=batch_number,
                expiry_date=expiry_date,
                quantity_received=qty,
                unit_cost=unit_cost,
                user=performer,
            )

    except PurchaseReceivingError:
        raise
    except Exception as exc:
        raise PurchaseReceivingError(
            f"Stock intake failed: {exc}"
        ) from exc

    invoice.subtotal_amount = subtotal
    invoice.total_amount = total
    invoice.status = PurchaseInvoice.STATUS_RECEIVED
    invoice.received_at = timezone.now()

    invoice.save(
        update_fields=[
            "subtotal_amount",
            "total_amount",
            "status",
            "received_at",
        ]
    )

    publish(
        GoodsReceived(
            invoice_id=str(invoice.id),
            supplier_id=getattr(invoice, "supplier_id", None),
            total_amount=total,
        )
    )

    return {
        "invoice_id": str(invoice.id),
        "status": invoice.status,
        "subtotal_amount": str(invoice.subtotal_amount),
        "total_amount": str(invoice.total_amount),
        "journal_entry_id": str(je.id),
    }