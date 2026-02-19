from django.contrib import admin

from .models import Cart, CartItem

# =====================================================
# CART ITEM INLINE (READ-ONLY)
# =====================================================


class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0
    can_delete = False
    readonly_fields = (
        "product",
        "quantity",
        "unit_price",
        "line_total",
        "created_at",
    )

    def has_add_permission(self, request, obj=None):
        return False


# =====================================================
# CART ADMIN
# =====================================================


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "is_active",
        "created_at",
        "subtotal_amount",
        "item_count",
    )

    readonly_fields = (
        "id",
        "user",
        "is_active",
        "created_at",
        "updated_at",
        "subtotal_amount",
        "item_count",
    )

    search_fields = ("user__email",)
    list_filter = ("is_active", "created_at")

    inlines = [CartItemInline]


# =====================================================
# CART ITEM ADMIN (FULLY IMMUTABLE)
# =====================================================


@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "cart",
        "product",
        "quantity",
        "unit_price",
        "line_total",
        "created_at",
    )

    readonly_fields = (
        "id",
        "cart",
        "product",
        "quantity",
        "unit_price",
        "line_total",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
