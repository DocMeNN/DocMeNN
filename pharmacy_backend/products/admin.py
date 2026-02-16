# products/admin.py
"""
=====================================================
PATH: products/admin.py
=====================================================

Admin rules (audit-safe stock intake):

- Product is created once.
- Stock comes in as StockBatch rows (delivery-based inventory).
- NEW inline rows are not saved directly; they are routed through intake_stock()
  to guarantee:
    - StockBatch created correctly (store-scoped, immutable)
    - StockMovement(RECEIPT) created (audit trail)
- Existing StockBatch rows are immutable and cannot be edited or deleted.

Important:
- Validation MUST happen inside InlineFormSet.clean() so Django admin can render
  inline errors on the page (instead of crashing into a ValidationError screen).

CRITICAL BUG FIX (UUID default PK):
- StockBatch.id is UUID with default=uuid4.
- Unsaved inline instances can already have a pk value.
- Therefore: NEVER use "inst.pk is truthy" to detect "existing row".
  Instead detect persisted rows by checking DB existence.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.contrib import admin
from django.core.exceptions import ValidationError
from django.forms.models import BaseInlineFormSet
from django.utils import timezone

from products.models import Product, Category, StockBatch
from products.services.stock_intake import intake_stock


# =====================================================
# HELPERS
# =====================================================

def _is_persisted_stockbatch(inst: StockBatch | None) -> bool:
    """
    Return True only if this StockBatch is already saved in DB.

    Why:
    - UUIDField(default=uuid4) means new, unsaved instances may still have pk.
    - So we must confirm DB existence (or _state.adding False).
    """
    if inst is None:
        return False

    # If Django already marks it as not-adding, it's persisted.
    if getattr(inst._state, "adding", True) is False:
        return True

    # Otherwise, confirm in DB (safe + accurate).
    pk = getattr(inst, "pk", None)
    if not pk:
        return False
    return StockBatch.objects.filter(pk=pk).exists()


def _is_blank_new_row(cd: dict) -> bool:
    batch_number = (cd.get("batch_number") or "").strip()
    expiry_date = cd.get("expiry_date")
    qty = cd.get("quantity_received")
    unit_cost = cd.get("unit_cost")

    return (
        (not batch_number)
        and (not expiry_date)
        and (qty in (None, "", 0))
        and (unit_cost in (None, "", "null"))
    )


# =====================================================
# CATEGORY
# =====================================================

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)
    ordering = ("name",)


# =====================================================
# INLINE FORMSET (VALIDATION LIVES HERE)
# =====================================================

class StockBatchInlineFormSet(BaseInlineFormSet):
    """
    Validates StockBatch inline entries.

    Key design:
    - Raise ValidationError here (clean) => admin shows errors nicely.
    - save_formset() should not raise user-facing ValidationError screens.
    """

    def clean(self):
        super().clean()

        parent_product = getattr(self, "instance", None)

        # Parent Product must have store selected (your service requires it)
        store_id = getattr(parent_product, "store_id", None)
        if not store_id:
            raise ValidationError("Select a Store on the Product before adding stock batches.")

        any_errors = False

        for form in self.forms:
            cd = getattr(form, "cleaned_data", None)
            if cd is None:
                continue

            # Block deletions (audit safety)
            if cd.get("DELETE"):
                form.add_error(None, "Stock batches are audit artifacts and cannot be deleted.")
                any_errors = True
                continue

            inst = getattr(form, "instance", None)
            persisted = _is_persisted_stockbatch(inst)

            # Existing rows are immutable: any edit attempt is blocked
            if persisted:
                if form.has_changed():
                    form.add_error(
                        None,
                        "Existing StockBatch rows are immutable. "
                        "Create a new batch for a new delivery instead of editing past deliveries.",
                    )
                    any_errors = True
                continue

            # New row: allow empty extra rows
            if _is_blank_new_row(cd):
                continue

            # Required: expiry_date
            expiry_date = cd.get("expiry_date")
            if not expiry_date:
                form.add_error("expiry_date", "expiry_date is required for stock intake.")
                any_errors = True

            # Required: quantity_received (int > 0)
            qty = cd.get("quantity_received")
            if qty in (None, ""):
                form.add_error("quantity_received", "quantity_received is required.")
                any_errors = True
            else:
                try:
                    qty_int = int(qty)
                    if qty_int <= 0:
                        form.add_error("quantity_received", "quantity_received must be > 0.")
                        any_errors = True
                except Exception:
                    form.add_error("quantity_received", "quantity_received must be a whole number.")
                    any_errors = True

            # Required: unit_cost (Decimal > 0)
            unit_cost = cd.get("unit_cost")
            if unit_cost in (None, "", "null"):
                form.add_error("unit_cost", "unit_cost is required for stock intake.")
                any_errors = True
            else:
                try:
                    uc = Decimal(str(unit_cost))
                    if uc <= Decimal("0.00"):
                        form.add_error("unit_cost", "unit_cost must be > 0.")
                        any_errors = True
                except (InvalidOperation, ValueError, TypeError):
                    form.add_error("unit_cost", "unit_cost must be a valid decimal.")
                    any_errors = True

            # Optional: if batch_number provided and product exists, enforce uniqueness
            batch_number = (cd.get("batch_number") or "").strip()
            product_id = getattr(parent_product, "id", None)

            if batch_number and product_id:
                exists = StockBatch.objects.filter(
                    store_id=store_id,
                    product_id=product_id,
                    batch_number=batch_number,
                ).exists()
                if exists:
                    form.add_error(
                        "batch_number",
                        "This batch_number already exists for this store + product. Use a unique value.",
                    )
                    any_errors = True

        if any_errors:
            raise ValidationError("Please correct the stock intake errors below.")


# =====================================================
# STOCK BATCH INLINE
# =====================================================

class StockBatchInline(admin.TabularInline):
    """
    Fused intake UI: add stock batches directly on the Product page.

    - New rows => intake_stock()
    - Existing rows => immutable
    """

    model = StockBatch
    formset = StockBatchInlineFormSet

    extra = 1
    can_delete = False
    show_change_link = False

    fields = (
        "batch_number",
        "expiry_date",
        "quantity_received",
        "unit_cost",
        "quantity_remaining",
        "is_active",
        "created_at",
    )
    readonly_fields = (
        "quantity_remaining",
        "is_active",
        "created_at",
    )

    def get_formset(self, request, obj=None, **kwargs):
        """
        batch_number is optional; intake_stock() will auto-generate one if blank.
        """
        formset = super().get_formset(request, obj, **kwargs)
        base_fields = getattr(formset.form, "base_fields", {})
        if "batch_number" in base_fields:
            base_fields["batch_number"].required = False
        return formset


# =====================================================
# PRODUCT
# =====================================================

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "sku",
        "name",
        "category",
        "unit_price",
        "total_stock_db",
        "is_low_stock",
        "is_active",
        "created_at",
    )
    list_filter = ("is_active", "category", "created_at")
    search_fields = ("sku", "name")
    ordering = ("-created_at",)
    readonly_fields = ("created_at", "updated_at")

    inlines = [StockBatchInline]

    def save_formset(self, request, form, formset, change):
        """
        Route NEW StockBatch rows through intake_stock().

        Notes:
        - Validation already happened in StockBatchInlineFormSet.clean()
        - We do NOT call formset.save() for StockBatch rows.
        - Django admin expects new_objects/changed_objects/deleted_objects to exist.
        """
        parent_product = form.instance

        if formset.model is not StockBatch:
            return super().save_formset(request, form, formset, change)

        created_batches = []

        for f in getattr(formset, "forms", []):
            cd = getattr(f, "cleaned_data", None)
            if not cd:
                continue
            if cd.get("DELETE"):
                continue

            inst = getattr(f, "instance", None)
            if _is_persisted_stockbatch(inst):
                continue

            if _is_blank_new_row(cd):
                continue

            batch_number = (cd.get("batch_number") or "").strip() or None
            expiry_date = cd.get("expiry_date")
            qty = cd.get("quantity_received")
            unit_cost = cd.get("unit_cost")

            batch = intake_stock(
                product=parent_product,
                quantity_received=int(qty),
                unit_cost=unit_cost,
                expiry_date=expiry_date,
                batch_number=batch_number,
                user=request.user,
                store=getattr(parent_product, "store", None) or getattr(parent_product, "store_id", None),
                update_product_price=False,
            )
            created_batches.append(batch)

        # Django admin compatibility: needed for the "added/changed" log message builder
        formset.new_objects = created_batches
        formset.changed_objects = []
        formset.deleted_objects = []

        if hasattr(formset, "save_m2m"):
            formset.save_m2m()


# =====================================================
# STOCK BATCH (VIEW-ONLY LIST)
# =====================================================

@admin.register(StockBatch)
class StockBatchAdmin(admin.ModelAdmin):
    """
    View-only stock batch list for audit visibility.
    Intake should happen via Product inline or API.
    """

    list_display = (
        "product",
        "batch_number",
        "expiry_date",
        "quantity_received",
        "unit_cost",
        "quantity_remaining",
        "expiry_status",
        "is_active",
        "created_at",
    )

    list_filter = ("is_active", "expiry_date", "created_at")
    search_fields = ("batch_number", "product__name", "product__sku")
    ordering = ("expiry_date", "created_at")

    readonly_fields = (
        "product",
        "batch_number",
        "expiry_date",
        "quantity_received",
        "unit_cost",
        "quantity_remaining",
        "is_active",
        "created_at",
    )

    def has_change_permission(self, request, obj=None):
        return False if obj else True

    def has_delete_permission(self, request, obj=None):
        return False

    def expiry_status(self, obj):
        today = timezone.localdate()

        if obj.expiry_date < today:
            return "❌ EXPIRED"

        if obj.expiry_date <= today + timedelta(days=30):
            return "⚠ SOON"

        return "OK"

    expiry_status.short_description = "Expiry Status"
