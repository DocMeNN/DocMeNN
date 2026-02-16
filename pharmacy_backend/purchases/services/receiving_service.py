# purchases/services/receiving_service.py


"""
======================================================
PATH: purchases/services/receiving_service.py
======================================================
PURCHASE RECEIVING SERVICE

Receive a PurchaseInvoice atomically (profit-ready, cost-snapshot safe):

Canonical flow (HOTSPRINT UPGRADE):
1) Lock invoice
2) Validate status + items
3) Post ledger FIRST (idempotent)
4) Intake stock (canonical): create StockBatch + create RECEIPT movement with unit_cost_snapshot
5) Mark invoice received

Why we changed this:
- COGS posting depends on StockMovement.unit_cost_snapshot.
- Receipt movements MUST carry unit_cost_snapshot.
- Therefore, purchase receiving MUST use inventory.intake_stock() (canonical),
  NOT receive_stock() (legacy repair only).

Idempotency rule:
- If ledger posting already exists (IdempotencyError), we treat it as success,
  load the existing JournalEntry by reference, and continue safely.
- Stock intake is also idempotent for exact replays: if the batch already exists and matches
  (product+batch_number+expiry+qty+unit_cost), we reuse it; otherwise we raise a conflict.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.utils import timezone

from accounting.models.account import Account
from accounting.models.journal import JournalEntry
from accounting.services.account_resolver import (
    get_active_chart,
    get_inventory_account,
    get_accounts_payable_account,
)
from accounting.services.exceptions import (
    AccountResolutionError,
    JournalEntryCreationError,
    IdempotencyError,
)
from accounting.services.posting import post_purchase_receipt_to_ledger

from products.models.stock_batch import StockBatch
from products.services.inventory import intake_stock

from purchases.models import PurchaseInvoice


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
    """
    Supports two modes:
    - Mode A: caller supplies account codes
    - Mode B: if blank, auto-resolve from chart via semantic mapping
    """
    inv_code = (inventory_account_code or "").strip()
    ap_code = (payable_account_code or "").strip()

    inventory_account = _resolve_account_by_code(code=inv_code) if inv_code else get_inventory_account()
    payable_account = _resolve_account_by_code(code=ap_code) if ap_code else get_accounts_payable_account()

    return inventory_account, payable_account


def _get_existing_purchase_receipt_journal_entry(*, invoice_id: str) -> JournalEntry:
    """
    JournalEntry reference is normalized in the engine as: f"{reference_type}:{reference_id}"
    For purchase receipt posting, we use:
        reference_type="PURCHASE_RECEIPT"
        reference_id=str(invoice_id)
    """
    ref = f"PURCHASE_RECEIPT:{str(invoice_id).strip()}"
    try:
        return JournalEntry.objects.get(reference=ref)
    except JournalEntry.DoesNotExist as exc:
        raise PurchaseReceivingError(
            "Ledger posting already exists (idempotency), but the journal entry could not be found by reference. "
            f"Expected reference={ref}."
        ) from exc


def _batch_conflict_guard(*, product, batch_number: str, expiry_date, qty: int, unit_cost: Decimal) -> None:
    """
    Protect against accidentally reusing a batch_number that belongs to a different real-world delivery.

    Rule:
    - If a StockBatch exists for (product, batch_number), it must match (expiry_date, quantity_received, unit_cost)
      for us to treat it as an idempotent replay. Otherwise, raise a clear conflict.
    """
    existing = StockBatch.objects.filter(product=product, batch_number=batch_number).first()
    if not existing:
        return

    ex_exp = getattr(existing, "expiry_date", None)
    ex_qty = int(getattr(existing, "quantity_received", 0) or 0)
    ex_cost_raw = getattr(existing, "unit_cost", None)

    try:
        ex_cost = _money(ex_cost_raw)
    except Exception:
        ex_cost = None

    # If unit_cost isn't set on existing, intake_stock() will backfill it;
    # we still compare if we can.
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
    """
    RECEIVE PURCHASE INVOICE (atomic)

    Canonical flow:
      1) Lock invoice
      2) Validate status + items
      3) Post ledger FIRST (idempotent)
      4) Intake stock (canonical): create StockBatch + RECEIPT movement with unit_cost_snapshot
      5) Mark invoice received
    """
    try:
        invoice = (
            PurchaseInvoice.objects.select_for_update()
            .prefetch_related("items", "items__product")
            .get(id=invoice_id)
        )
    except PurchaseInvoice.DoesNotExist as exc:
        raise PurchaseReceivingError("Purchase invoice not found") from exc

    # Idempotent behavior: if already received, return state (do not re-receive).
    if invoice.status == PurchaseInvoice.STATUS_RECEIVED:
        try:
            je = _get_existing_purchase_receipt_journal_entry(invoice_id=str(invoice.id))
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

    # ------------------------------
    # Validate lines + compute totals
    # ------------------------------
    subtotal = Decimal("0.00")

    for it in items:
        if it.quantity <= 0:
            raise PurchaseReceivingError("Item quantity must be > 0")

        if it.unit_cost in (None, "", "null"):
            raise PurchaseReceivingError("Item unit_cost is required")

        if Decimal(str(it.unit_cost)) < Decimal("0.00"):
            raise PurchaseReceivingError("Item unit_cost cannot be negative")

        if not (it.batch_number or "").strip():
            raise PurchaseReceivingError("Item batch_number is required (supplier delivery batch reference)")

        if not it.expiry_date:
            raise PurchaseReceivingError("Item expiry_date is required")

        subtotal += it.line_total

    subtotal = _money(subtotal)
    total = subtotal  # tax/discount later

    # Prefer invoice-specific received date if present later; for now canonical receive date:
    received_date = timezone.localdate()

    # ------------------------------
    # Post ledger FIRST (idempotent)
    # ------------------------------
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
        # Idempotent retry: ledger is already posted; continue safely.
        je = _get_existing_purchase_receipt_journal_entry(invoice_id=str(invoice.id))
    except JournalEntryCreationError as exc:
        raise PurchaseReceivingError(str(exc)) from exc
    except Exception as exc:
        raise PurchaseReceivingError(f"Failed to post purchase receipt: {exc}") from exc

    # ------------------------------
    # Intake stock (canonical)
    # ------------------------------
    performer = getattr(invoice, "created_by", None)

    try:
        for it in items:
            product = it.product
            batch_number = (it.batch_number or "").strip()
            expiry_date = it.expiry_date
            qty = int(it.quantity)
            unit_cost = _money(it.unit_cost)

            # Prevent silent reuse of same batch_number for different deliveries
            _batch_conflict_guard(
                product=product,
                batch_number=batch_number,
                expiry_date=expiry_date,
                qty=qty,
                unit_cost=unit_cost,
            )

            # Canonical: creates StockBatch + RECEIPT movement with unit_cost_snapshot
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
        raise PurchaseReceivingError(f"Stock intake failed: {exc}") from exc

    # ------------------------------
    # Mark invoice received
    # ------------------------------
    invoice.subtotal_amount = subtotal
    invoice.total_amount = total
    invoice.status = PurchaseInvoice.STATUS_RECEIVED
    invoice.received_at = timezone.now()
    invoice.save(update_fields=["subtotal_amount", "total_amount", "status", "received_at"])

    return {
        "invoice_id": str(invoice.id),
        "status": invoice.status,
        "subtotal_amount": str(invoice.subtotal_amount),
        "total_amount": str(invoice.total_amount),
        "journal_entry_id": str(je.id),
    }
