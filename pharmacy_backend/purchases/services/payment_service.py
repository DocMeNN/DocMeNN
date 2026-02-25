# purchases/services/payment_service.py

from decimal import ROUND_HALF_UP, Decimal
import logging

from django.db import transaction
from django.utils import timezone

from accounting.models.account import Account
from accounting.services.account_resolver import (
    get_accounts_payable_account,
    get_active_chart,
    get_bank_account,
    get_cash_account,
)
from accounting.services.exceptions import (
    AccountResolutionError,
    IdempotencyError,
    JournalEntryCreationError,
)
from accounting.services.posting import post_supplier_payment_to_ledger
from purchases.models import PurchaseInvoice, Supplier, SupplierPayment


logger = logging.getLogger("payments")


class SupplierPaymentError(ValueError):
    pass


TWOPLACES = Decimal("0.01")


def _money(v) -> Decimal:
    return Decimal(str(v or "0.00")).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def _resolve_account_by_code(*, code: str) -> Account:
    chart = get_active_chart()
    code = (code or "").strip()
    if not code:
        logger.error("Account resolution failed: empty account code provided")
        raise SupplierPaymentError("Account code is required")

    try:
        return Account.objects.get(chart=chart, code=code, is_active=True)
    except Account.DoesNotExist as exc:
        logger.error(
            "Account resolution failed: account not found",
            extra={"account_code": code, "chart": getattr(chart, "name", None)},
        )
        raise AccountResolutionError(
            f"Account with code={code} not found in active chart ({getattr(chart, 'name', 'ACTIVE_CHART')})."
        ) from exc
    except Account.MultipleObjectsReturned as exc:
        logger.error(
            "Account resolution failed: multiple accounts found",
            extra={"account_code": code, "chart": getattr(chart, "name", None)},
        )
        raise AccountResolutionError(
            f"Multiple active accounts found with code={code} in active chart ({getattr(chart, 'name', 'ACTIVE_CHART')}). "
            "Account codes must be unique per chart."
        ) from exc


def _resolve_payment_account(
    *, payment_method: str, payment_account_code: str | None
) -> Account:
    code = (payment_account_code or "").strip()
    if code:
        return _resolve_account_by_code(code=code)

    m = (payment_method or "cash").lower().strip()
    if m == "cash":
        return get_cash_account()
    if m in ("bank", "transfer", "card"):
        return get_bank_account()

    logger.error(
        "Invalid payment method provided",
        extra={"payment_method": payment_method},
    )
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
    """

    logger.info(
        "Initiating supplier payment",
        extra={
            "supplier_id": supplier_id,
            "invoice_id": invoice_id,
            "amount": str(amount),
            "payment_method": payment_method,
        },
    )

    try:
        supplier = Supplier.objects.get(id=supplier_id, is_active=True)
    except Supplier.DoesNotExist as exc:
        logger.error(
            "Supplier not found during payment",
            extra={"supplier_id": supplier_id},
        )
        raise SupplierPaymentError("Supplier not found") from exc

    invoice = None
    if invoice_id:
        try:
            invoice = PurchaseInvoice.objects.get(id=invoice_id, supplier=supplier)
        except PurchaseInvoice.DoesNotExist as exc:
            logger.error(
                "Invoice not found for supplier",
                extra={"invoice_id": invoice_id, "supplier_id": supplier_id},
            )
            raise SupplierPaymentError("Invoice not found for supplier") from exc

    amt = _money(amount)
    if amt <= Decimal("0.00"):
        logger.error(
            "Invalid payment amount",
            extra={"amount": str(amount)},
        )
        raise SupplierPaymentError("Amount must be > 0")

    pay_date = payment_date or timezone.now().date()

    try:
        ap_code = (payable_account_code or "").strip()
        payable_account = (
            _resolve_account_by_code(code=ap_code)
            if ap_code
            else get_accounts_payable_account()
        )

        payment_account = _resolve_payment_account(
            payment_method=payment_method,
            payment_account_code=payment_account_code,
        )
    except Exception:
        logger.exception("Account resolution failed during supplier payment")
        raise

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
        logger.error(
            "Journal entry creation failed for supplier payment",
            extra={"payment_id": str(payment.id)},
        )
        transaction.set_rollback(True)
        raise SupplierPaymentError(str(exc)) from exc
    except Exception:
        logger.exception(
            "Unexpected failure posting supplier payment to ledger",
            extra={"payment_id": str(payment.id)},
        )
        transaction.set_rollback(True)
        raise SupplierPaymentError("Failed to post supplier payment")

    logger.info(
        "Supplier payment completed successfully",
        extra={
            "payment_id": str(payment.id),
            "journal_entry_id": je.id,
        },
    )

    return {
        "payment_id": str(payment.id),
        "supplier_id": str(supplier.id),
        "invoice_id": str(invoice.id) if invoice else None,
        "payment_date": str(pay_date),
        "amount": str(payment.amount),
        "payment_method": payment.payment_method,
        "journal_entry_id": je.id,
    }