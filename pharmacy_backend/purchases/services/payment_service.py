# purchases/services/payment_service.py

from decimal import Decimal, ROUND_HALF_UP
from django.db import transaction
from django.utils import timezone

from accounting.models.account import Account
from accounting.services.account_resolver import (
    get_active_chart,
    get_cash_account,
    get_bank_account,
    get_accounts_payable_account,
)
from accounting.services.posting import post_supplier_payment_to_ledger
from accounting.services.exceptions import AccountResolutionError, JournalEntryCreationError, IdempotencyError

from purchases.models import Supplier, PurchaseInvoice, SupplierPayment


class SupplierPaymentError(ValueError):
    pass


TWOPLACES = Decimal("0.01")


def _money(v) -> Decimal:
    return Decimal(str(v or "0.00")).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def _resolve_account_by_code(*, code: str) -> Account:
    chart = get_active_chart()
    code = (code or "").strip()
    if not code:
        raise SupplierPaymentError("Account code is required")

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


def _resolve_payment_account(*, payment_method: str, payment_account_code: str | None) -> Account:
    """
    - If payment_account_code provided -> use it
    - Else auto-resolve from method:
        cash -> Cash
        bank/transfer/card -> Bank
    """
    code = (payment_account_code or "").strip()
    if code:
        return _resolve_account_by_code(code=code)

    m = (payment_method or "cash").lower().strip()
    if m == "cash":
        return get_cash_account()
    if m in ("bank", "transfer", "card"):
        return get_bank_account()

    raise SupplierPaymentError("Invalid payment_method. Use 'cash' or 'bank'.")


@transaction.atomic
def pay_supplier_invoice(
    *,
    supplier_id,
    invoice_id=None,
    payment_date=None,
    amount=None,
    payment_method: str,
    narration: str = "",
    payable_account_code: str | None = None,
    payment_account_code: str | None = None,
):
    """
    CREATE SUPPLIER PAYMENT (atomic)

    Flow:
      1) Validate supplier (and invoice if provided)
      2) Create SupplierPayment row
      3) Post ledger FIRST (idempotent)
      4) Return receipt
    """
    try:
        supplier = Supplier.objects.get(id=supplier_id, is_active=True)
    except Supplier.DoesNotExist as exc:
        raise SupplierPaymentError("Supplier not found") from exc

    invoice = None
    if invoice_id:
        try:
            invoice = PurchaseInvoice.objects.get(id=invoice_id, supplier=supplier)
        except PurchaseInvoice.DoesNotExist as exc:
            raise SupplierPaymentError("Invoice not found for supplier") from exc

    amt = _money(amount)
    if amt <= Decimal("0.00"):
        raise SupplierPaymentError("Amount must be > 0")

    pay_date = payment_date or timezone.now().date()

    # Resolve Accounts Payable (allow override by code)
    ap_code = (payable_account_code or "").strip()
    payable_account = _resolve_account_by_code(code=ap_code) if ap_code else get_accounts_payable_account()

    # Resolve Cash/Bank (allow override by code)
    payment_account = _resolve_payment_account(
        payment_method=payment_method,
        payment_account_code=payment_account_code,
    )

    payment = SupplierPayment.objects.create(
        supplier=supplier,
        invoice=invoice,
        payment_date=pay_date,
        amount=amt,
        payment_method=(payment_method or "cash").lower().strip(),
        narration=narration or "",
    )

    try:
        je = post_supplier_payment_to_ledger(
            payment_id=str(payment.id),
            payment_date=pay_date,
            payable_account=payable_account,
            payment_account=payment_account,
            amount=amt,
            supplier_name=supplier.name,
            invoice_number=(invoice.invoice_number if invoice else ""),
        )
    except (IdempotencyError, JournalEntryCreationError) as exc:
        transaction.set_rollback(True)
        raise SupplierPaymentError(str(exc)) from exc
    except Exception as exc:
        transaction.set_rollback(True)
        raise SupplierPaymentError(f"Failed to post supplier payment: {exc}") from exc

    return {
        "payment_id": str(payment.id),
        "supplier_id": str(supplier.id),
        "invoice_id": str(invoice.id) if invoice else None,
        "payment_date": str(pay_date),
        "amount": str(payment.amount),
        "payment_method": payment.payment_method,
        "journal_entry_id": je.id,
    }
