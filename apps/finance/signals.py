from django.db.models.signals import post_save, post_migrate
from django.dispatch import receiver

from apps.products.models import Order, Product
from apps.accounts.models import CustomUser

from .models import (
    Account,
    ExpenseCategory,
)
from .services import (
    create_sales_voucher,
    create_account_opening_journal,
)


# ==========================================================
# 1. CREATE SALES VOUCHER AUTOMATICALLY WHEN ORDER ACCEPTED
# ==========================================================

@receiver(post_save, sender=Order)
def create_order_sales_voucher(sender, instance, created, **kwargs):
    """
    Automatically creates a Sales Voucher (Journal + Entries)
    when an Order status changes to 'accepted'.
    """
    if created:
        return

    # Trigger only when order is accepted
    if instance.status != "accepted":
        return

    # Check if a Sales Voucher already exists for this order
    if instance.journals.filter(voucher_type="sales").exists():
        return

    # Call Sales Voucher Service
    create_sales_voucher(instance)


# ==========================================================
# 2. CREATE CUSTOMER ACCOUNT AUTOMATICALLY
# ==========================================================

@receiver(post_save, sender=CustomUser)
def create_customer_account(sender, instance, created, **kwargs):
    """
    Automatically creates a Customer Account in the Chart of Accounts
    when a new regular user registers.
    """
    if not created:
        return

    # Do not auto-create customer account for staff/superusers
    if instance.is_staff or instance.is_superuser:
        return

    account, account_created = Account.objects.get_or_create(
        customer=instance,
        defaults={
            "name": f"Customer: {instance.username or instance.first_name or instance.email}",
            "type1": "asset",
            "type2": "customer",
            "status": "active",
        },
    )

    # Check if opening balance needs to be journalized
    if account_created and account.opening_balance > 0:
        create_account_opening_journal(account)


# ==========================================================
# 3. CREATE PRODUCT ACCOUNT AUTOMATICALLY
# ==========================================================

@receiver(post_save, sender=Product)
def create_product_account(sender, instance, created, **kwargs):
    """
    Automatically creates a Revenue Account in Chart of Accounts
    when a new product is created.
    """
    if not created:
        return

    Account.objects.get_or_create(
        product=instance,
        defaults={
            "name": f"Sales Revenue - {instance.name}",
            "type1": "revenue",
            "type2": "product",
            "status": "active",
        },
    )


# ==========================================================
# 4. CREATE EXPENSE ACCOUNT AUTOMATICALLY
# ==========================================================

@receiver(post_save, sender=ExpenseCategory)
def create_expense_account(sender, instance, created, **kwargs):
    """
    Automatically creates an Expense Account in Chart of Accounts
    when a new Expense Category is created.
    """
    if not created:
        return

    Account.objects.get_or_create(
        expense_category=instance,
        defaults={
            "name": f"Expense: {instance.name}",
            "type1": "expense",
            "type2": "other",
            "status": "active",
        },
    )


# ==========================================================
# 5. CREATE DEFAULT SYSTEM ACCOUNTS (POST MIGRATE)
# ==========================================================

@receiver(post_migrate)
def create_default_system_accounts(sender, **kwargs):
    """
    Ensures that default System Accounts (Cash, Bank, Discount,
    Packaging Charge, bKash Charge, Opening Equity) exist.
    """
    # Restrict signal execution to the target finance app only
    if sender.name != "apps.finance":
        return

    default_accounts = [
        # Cash Account
        {
            "name": "Cash",
            "type1": "asset",
            "type2": "cash",
            "is_default": True,
            "status": "active",
        },
        # Bank Account
        {
            "name": "Main Bank Account",
            "type1": "asset",
            "type2": "bank",
            "is_default": True,
            "status": "active",
        },
        # Sales Discount Account
        {
            "name": "Sales Discount",
            "type1": "expense",
            "type2": "discount",
            "is_default": True,
            "status": "active",
        },
        # Packaging Charge Account
        {
            "name": "Packaging Charge Revenue",
            "type1": "revenue",
            "type2": "packaging",
            "is_default": True,
            "status": "active",
        },
        # bKash Charge Account
        {
            "name": "bKash Charge Revenue",
            "type1": "revenue",
            "type2": "bkash_charge",
            "is_default": True,
            "status": "active",
        },
        # Opening Balance Equity
        {
            "name": "Opening Balance Equity",
            "type1": "equity",
            "type2": "capital",
            "is_default": True,
            "status": "active",
        },
    ]

    for account_data in default_accounts:
        Account.objects.get_or_create(
            name=account_data["name"],
            defaults=account_data,
        )