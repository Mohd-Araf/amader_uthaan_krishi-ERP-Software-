
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
# 1. CREATE / UPDATE SALES VOUCHER WHEN ORDER IS ACCEPTED
# ==========================================================

@receiver(post_save, sender=Order)
def create_order_sales_voucher(sender, instance, created, **kwargs):
    """
    Automatically creates or updates a Sales Voucher (Journal + Entries)
    when an Order status is 'accepted'.
    """
    # Trigger only when order status is accepted
    if instance.status != "accepted":
        return

    # Call Sales Voucher Service to create or sync updated items/charges
    create_sales_voucher(instance)


# ==========================================================
# 2. TRIGGER OPENING BALANCE JOURNAL WHEN ACCOUNT HAS OPENING BALANCE
# ==========================================================

@receiver(post_save, sender=Account)
def trigger_account_opening_journal(sender, instance, created, **kwargs):
    """
    Automatically generates an Opening Balance Journal Voucher whenever an
    Account has an opening_balance > 0.
    """
    if instance.opening_balance and instance.opening_balance > 0:
        create_account_opening_journal(instance)


# ==========================================================
# 3. CREATE / UPDATE USER ACCOUNT AUTOMATICALLY
# ==========================================================

@receiver(post_save, sender=CustomUser)
def sync_user_account(sender, instance, created, **kwargs):
    """
    Automatically creates or updates the Chart of Accounts
    account associated with a CustomUser.

    Normal user  -> Customer Account
    Staff user   -> Supplier Account
    Superuser    -> No party account
    """

    # ------------------------------------------------------
    # Superuser should not have customer/supplier account
    # ------------------------------------------------------
    if instance.is_superuser:
        return

    # ------------------------------------------------------
    # Determine account type based on user status
    # ------------------------------------------------------
    if instance.is_staff:
        # Staff = Supplier
        type1 = "liability"
        type2 = "supplier"
        name = (
            f"Supplier: "
            f"{instance.username or instance.first_name or instance.email}"
        )
    else:
        # Normal user = Customer
        type1 = "asset"
        type2 = "customer"
        name = (
            f"Customer: "
            f"{instance.username or instance.first_name or instance.email}"
        )

    # ------------------------------------------------------
    # Find existing account
    # ------------------------------------------------------
    account = Account.objects.filter(customer=instance).first()

    # ------------------------------------------------------
    # Create if account does not exist
    # ------------------------------------------------------
    if not account:
        account = Account.objects.create(
            customer=instance,
            name=name,
            type1=type1,
            type2=type2,
            status="active",
        )

    # ------------------------------------------------------
    # Update existing account
    # ------------------------------------------------------
    else:
        account.name = name
        account.type1 = type1
        account.type2 = type2
        account.status = "active"
        account.save(
            update_fields=[
                "name",
                "type1",
                "type2",
                "status",
                "updated_at",
            ]
        )

# ==========================================================
# 4. CREATE PRODUCT ACCOUNT AUTOMATICALLY
# ==========================================================

@receiver(post_save, sender=Product)
def create_product_account(sender, instance, created, **kwargs):

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
# 5. CREATE EXPENSE ACCOUNT AUTOMATICALLY
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



# 6. CREATE DEFAULT SYSTEM ACCOUNTS (POST MIGRATE)


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
        # Bad Debt (Expected Credit Loss) Account
        {
            "name": "Bad Debt (Expected Credit Loss)",
            "type1": "expense",
            "type2": "bad_debt",
            "is_default": True,
            "status": "active",
        },
    ]

    for account_data in default_accounts:
        Account.objects.get_or_create(
            name=account_data["name"],
            defaults=account_data,
        )
