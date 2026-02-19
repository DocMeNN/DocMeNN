# accounting/admin.py

from django.contrib import admin

from accounting.models.account import Account
from accounting.models.chart import ChartOfAccounts
from accounting.models.journal import JournalEntry
from accounting.models.ledger import LedgerEntry

# ============================================================
# CHART OF ACCOUNTS
# ============================================================


@admin.register(ChartOfAccounts)
class ChartOfAccountsAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "industry",
        "is_active",
        "created_at",
        "updated_at",
    )
    list_filter = ("industry", "is_active")
    search_fields = ("name", "industry")
    readonly_fields = ("created_at", "updated_at")
    ordering = ("name",)


# ============================================================
# ACCOUNT
# ============================================================


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "name",
        "account_type",
        "chart",
        "is_active",
    )
    list_filter = ("account_type", "is_active", "chart")
    search_fields = ("code", "name")
    ordering = ("chart", "code")
    readonly_fields = ("created_at", "updated_at")

    fieldsets = (
        (
            "Account Identity",
            {
                "fields": ("chart", "code", "name", "account_type"),
            },
        ),
        (
            "Status",
            {
                "fields": ("is_active",),
            },
        ),
        (
            "System Fields",
            {
                "fields": ("created_at", "updated_at"),
            },
        ),
    )


# ============================================================
# JOURNAL ENTRY (READ-ONLY)
# ============================================================


@admin.register(JournalEntry)
class JournalEntryAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "description",
        "reference",
        "posted_at",
        "is_posted",
        "created_at",
    )
    list_filter = ("is_posted", "posted_at")
    search_fields = ("description", "reference")
    ordering = ("-posted_at",)

    readonly_fields = (
        "reference",
        "description",
        "posted_at",
        "is_posted",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


# ============================================================
# LEDGER ENTRY (STRICTLY IMMUTABLE)
# ============================================================


@admin.register(LedgerEntry)
class LedgerEntryAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "journal_entry",
        "account",
        "entry_type",
        "amount",
        "created_at",
    )
    list_filter = ("entry_type", "account")
    search_fields = ("journal_entry__reference", "account__code")
    ordering = ("created_at",)

    readonly_fields = (
        "journal_entry",
        "account",
        "entry_type",
        "amount",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
