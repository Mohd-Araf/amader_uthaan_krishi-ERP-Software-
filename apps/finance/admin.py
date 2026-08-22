from django.contrib import admin

from .models import (
    Journal,
    JournalItem,
    Account,
    JournalEntry,
    PaymentReceipt,
    ExpenseCategory,
    Expense,
    VoucherPaymentLine,
)


# ==========================================================
# Voucher Payment Line Settlement Admin
# ==========================================================

@admin.register(VoucherPaymentLine)
class VoucherPaymentLineAdmin(admin.ModelAdmin):
    list_display = (
        "payment_journal",
        "reference_voucher",
        "account",
        "amount",
        "created_at",
    )

    search_fields = (
        "payment_journal__voucher_no",
        "reference_voucher__voucher_no",
        "account__name",
    )

    list_filter = (
        "created_at",
    )

    readonly_fields = (
        "created_at",
    )


# ==========================================================
# Expense Category
# ==========================================================

@admin.register(ExpenseCategory)
class ExpenseCategoryAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "is_active",
    )

    list_filter = (
        "is_active",
    )

    search_fields = (
        "name",
    )


# ==========================================================
# Expense
# ==========================================================

@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = (
        "category",
        "expense_account",
        "payment_account",
        "amount",
        "created_by",
        "expense_date",
    )

    list_filter = (
        "category",
        "expense_date",
    )

    search_fields = (
        "category__name",
        "expense_account__name",
        "remarks",
    )


# ==========================================================
# Payment Receipt
# ==========================================================

@admin.register(PaymentReceipt)
class PaymentReceiptAdmin(admin.ModelAdmin):
    list_display = (
        "payment_type",
        "party_account",
        "payment_account",
        "amount",
        "received_by",
        "received_at",
    )

    list_filter = (
        "payment_type",
        "received_at",
    )

    search_fields = (
        "party_account__name",
        "payment_account__name",
        "remarks",
    )


# ==========================================================
# Journal Item Inline
# ==========================================================

class JournalItemInline(admin.TabularInline):
    model = JournalItem
    extra = 0
    readonly_fields = (
        "product",
        "quantity",
        "rate",
        "amount",
    )


# ==========================================================
# Journal Entry Inline
# ==========================================================

class JournalEntryInline(admin.TabularInline):
    model = JournalEntry
    extra = 0
    readonly_fields = (
        "account",
        "debit",
        "credit",
        "entry_date",
    )


# ==========================================================
# Journal
# ==========================================================

@admin.register(Journal)
class JournalAdmin(admin.ModelAdmin):
    list_display = (
        "voucher_no",
        "journal_id",
        "voucher_type",
        "reference_type",
        "status",
        "get_total_debit",
        "get_total_credit",
        "created_at",
    )

    search_fields = (
        "voucher_no",
        "journal_id",
        "reference_no",
        "order__order_code",
        "notes",
    )

    list_filter = (
        "voucher_type",
        "reference_type",
        "status",
        "created_at",
    )

    readonly_fields = (
        "journal_id",
        "voucher_no",
        "created_at",
        "updated_at",
    )

    inlines = (
        JournalItemInline,
        JournalEntryInline,
    )

    @admin.display(description="Total Debit")
    def get_total_debit(self, obj):
        return f"৳ {obj.total_debit:,.2f}"

    @admin.display(description="Total Credit")
    def get_total_credit(self, obj):
        return f"৳ {obj.total_credit:,.2f}"


# ==========================================================
# Account
# ==========================================================

@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = (
        "account_code",
        "name",
        "type1",
        "type2",
        "customer",
        "product",
        "expense_category",
        "opening_balance",
        "get_current_balance",
        "is_default",
        "status",
        "created_at",
    )

    list_filter = (
        "type1",
        "type2",
        "status",
        "is_default",
    )

    search_fields = (
        "account_code",
        "name",
        "customer__username",
        "product__name",
        "expense_category__name",
    )

    readonly_fields = (
        "account_code",
        "created_at",
        "updated_at",
    )

    ordering = (
        "name",
    )

    @admin.display(description="Current Balance")
    def get_current_balance(self, obj):
        return f"৳ {obj.current_balance:,.2f}"


# ==========================================================
# Journal Entry
# ==========================================================

@admin.register(JournalEntry)
class JournalEntryAdmin(admin.ModelAdmin):
    list_display = (
        "voucher_no",
        "journal",
        "account",
        "debit",
        "credit",
        "entry_date",
    )

    list_filter = (
        "voucher_type",
        "account__type1",
        "account__type2",
        "entry_date",
    )

    search_fields = (
        "voucher_no",
        "journal__journal_id",
        "account__name",
        "narration",
    )