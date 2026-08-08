from decimal import Decimal, ROUND_HALF_UP
from django.db import transaction
from django.db.models import Sum
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.products.models import OrderItem, Order
from .models import (
    Journal,
    JournalItem,
    Account,
    JournalEntry,
    PaymentReceipt,
    Expense,
    ExpenseCategory,
)

TWO_DECIMAL = Decimal("0.01")


# ==========================================================
# 1. CREATE SALES VOUCHER (AUTOMATIC FROM ORDER)
# ==========================================================

@transaction.atomic
def create_sales_voucher(order: Order, created_by=None):
    """
    Sales Voucher Auto Generator for Orders.

    Double Entry Logic:
    -----------------------
    DR: Customer Account (Grand Total)
    DR: Sales Discount Account (if any)
    CR: Product Revenue Accounts (Sum of Items)
    CR: Packaging Charge Revenue (if any)
    CR: bKash Charge Revenue (if any)
    """

    # --------------------------------------
    # Check if Journal already exists
    # --------------------------------------
    if order.journals.filter(voucher_type="sales").exists():
        return order.journals.filter(voucher_type="sales").first()

    # --------------------------------------
    # Amounts Calculation
    # --------------------------------------
    subtotal = Decimal(str(order.updated_total_price or 0)).quantize(TWO_DECIMAL, rounding=ROUND_HALF_UP)
    discount = Decimal(str(order.discount or 0)).quantize(TWO_DECIMAL, rounding=ROUND_HALF_UP)
    packaging_charge = Decimal(str(order.packaging_charge or 0)).quantize(TWO_DECIMAL, rounding=ROUND_HALF_UP)
    bkash_charge = Decimal(str(order.bkash_charge or 0)).quantize(TWO_DECIMAL, rounding=ROUND_HALF_UP)
    grand_total = Decimal(str(order.final_payment or 0)).quantize(TWO_DECIMAL, rounding=ROUND_HALF_UP)

    # --------------------------------------
    # Customer Account
    # --------------------------------------
    customer_account, _ = Account.objects.get_or_create(
        customer=order.user,
        defaults={
            "name": f"Customer: {order.user.username}",
            "type1": "asset",
            "type2": "customer",
            "status": "active",
        },
    )

    # --------------------------------------
    # Default Accounts Setup
    # --------------------------------------
    discount_account, _ = Account.objects.get_or_create(
        type1="expense",
        type2="discount",
        is_default=True,
        defaults={"name": "Sales Discount", "status": "active"},
    )

    packaging_account, _ = Account.objects.get_or_create(
        type1="revenue",
        type2="packaging",
        is_default=True,
        defaults={"name": "Packaging Charge Revenue", "status": "active"},
    )

    bkash_account, _ = Account.objects.get_or_create(
        type1="revenue",
        type2="bkash_charge",
        is_default=True,
        defaults={"name": "bKash Charge Revenue", "status": "active"},
    )

    # --------------------------------------
    # Create Journal Voucher Header
    # --------------------------------------
    journal = Journal.objects.create(
        order=order,
        voucher_type="sales",
        reference_type="invoice",
        reference_no=order.order_code,
        notes=f"Sales Invoice for Order #{order.order_code}",
        status="posted",
        created_by=created_by,
        posted_by=created_by,
        posted_at=timezone.now()
    )

    ZERO = Decimal("0.00")

    # --------------------------------------
    # DR: Customer Account (Grand Total)
    # --------------------------------------
    JournalEntry.objects.create(
        journal=journal,
        account=customer_account,
        debit=grand_total,
        credit=ZERO,
        narration=f"Invoice #{order.order_code}",
        created_by=created_by,
    )

    # --------------------------------------
    # DR: Discount (if any)
    # --------------------------------------
    if discount > ZERO:
        JournalEntry.objects.create(
            journal=journal,
            account=discount_account,
            debit=discount,
            credit=ZERO,
            narration=f"Sales Discount for Order #{order.order_code}",
            created_by=created_by,
        )

    # --------------------------------------
    # CR: Packaging Charge (if any)
    # --------------------------------------
    if packaging_charge > ZERO:
        JournalEntry.objects.create(
            journal=journal,
            account=packaging_account,
            debit=ZERO,
            credit=packaging_charge,
            narration=f"Packaging Charge for Order #{order.order_code}",
            created_by=created_by,
        )

    # --------------------------------------
    # CR: bKash Charge (if any)
    # --------------------------------------
    if bkash_charge > ZERO:
        JournalEntry.objects.create(
            journal=journal,
            account=bkash_account,
            debit=ZERO,
            credit=bkash_charge,
            narration=f"bKash Charge for Order #{order.order_code}",
            created_by=created_by,
        )

    # --------------------------------------
    # CR: Products Revenue
    # --------------------------------------
    items = OrderItem.objects.filter(order=order).select_related("product")
    for item in items:
        qty = Decimal(str(item.updated_quantity if item.updated_quantity is not None else item.quantity))
        rate = Decimal(str(item.price_at_order_time if item.price_at_order_time is not None else item.product.price)).quantize(TWO_DECIMAL, rounding=ROUND_HALF_UP)
        amount = (qty * rate).quantize(TWO_DECIMAL, rounding=ROUND_HALF_UP)

        if amount <= ZERO:
            continue

        # Product Line Item History
        JournalItem.objects.create(
            journal=journal,
            product=item.product,
            quantity=qty,
            rate=rate,
            amount=amount,
            remark=getattr(item, "remarks", "") or f"Sold {item.product.name}",
        )

        # Product Revenue Account
        product_account, _ = Account.objects.get_or_create(
            product=item.product,
            defaults={
                "name": f"Sales Revenue - {item.product.name}",
                "type1": "revenue",
                "type2": "product",
                "status": "active",
            },
        )

        # Credit Product Account
        JournalEntry.objects.create(
            journal=journal,
            account=product_account,
            debit=ZERO,
            credit=amount,
            narration=f"Sold {item.product.name} (Qty: {qty})",
            created_by=created_by,
        )

    # --------------------------------------
    # Double-Entry Balance Check
    # --------------------------------------
    if not journal.is_balanced:
        raise ValidationError(
            f"Sales Journal for Order #{order.order_code} is not balanced! "
            f"Total Debit: {journal.total_debit}, Total Credit: {journal.total_credit}"
        )

    return journal


# ==========================================================
# 2. RECEIVE CUSTOMER PAYMENT SERVICE
# ==========================================================

@transaction.atomic
def receive_customer_payment(customer_account: Account, payment_account: Account = None, amount: Decimal = Decimal("0.00"), received_by=None, remarks="", journal=None):
    """
    Customer Receive Payment Service.

    Double Entry (Handled automatically by PaymentReceipt model save):
    DR: Cash / Bank Account
    CR: Customer Account
    """
    amount = Decimal(str(amount)).quantize(TWO_DECIMAL, rounding=ROUND_HALF_UP)
    if amount <= Decimal("0.00"):
        raise ValueError("Received amount must be greater than zero.")

    # Fallback to default Cash Account if payment_account is not specified
    if not payment_account:
        payment_account, _ = Account.objects.get_or_create(
            type2="cash",
            is_default=True,
            defaults={"name": "Cash", "type1": "asset", "status": "active"}
        )

    # If customer_account is passed via journal
    if journal and not customer_account:
        customer_account = journal.customer

    # Create Payment Record (This auto-creates Journal and JournalEntries)
    payment = PaymentReceipt.objects.create(
        payment_type="receipt",
        party_account=customer_account,
        payment_account=payment_account,
        amount=amount,
        remarks=remarks,
        received_by=received_by
    )

    return payment.journal or payment


# ==========================================================
# 3. MAKE SUPPLIER / PAYABLE PAYMENT SERVICE
# ==========================================================

@transaction.atomic
def make_supplier_payment(account: Account = None, payment_account: Account = None, amount: Decimal = Decimal("0.00"), created_by=None, remarks="", journal=None, paid_by=None, party_account=None):
    """
    Supplier / Liability Payment Service.

    Double Entry (Handled automatically by PaymentReceipt model save):
    DR: Supplier / Liability Account
    CR: Cash / Bank Account
    """
    target_party = party_account or account
    user = paid_by or created_by

    amount = Decimal(str(amount)).quantize(TWO_DECIMAL, rounding=ROUND_HALF_UP)
    if amount <= Decimal("0.00"):
        raise ValueError("Payment amount must be greater than zero.")

    # Fallback to default Cash Account if payment_account is not specified
    if not payment_account:
        payment_account, _ = Account.objects.get_or_create(
            type1="asset",
            type2="cash",
            is_default=True,
            defaults={"name": "Cash", "status": "active"}
        )

    # Create Payment Record (This auto-creates Journal and JournalEntries)
    payment = PaymentReceipt.objects.create(
        payment_type="payment",
        party_account=target_party,
        payment_account=payment_account,
        amount=amount,
        remarks=remarks,
        received_by=user
    )

    return payment.journal or payment


# ==========================================================
# 4. CREATE EXPENSE VOUCHER SERVICE
# ==========================================================

@transaction.atomic
def create_expense_voucher(category: ExpenseCategory, expense_account: Account, payment_account: Account, amount: Decimal, created_by=None, remarks=""):
    """
    Add Expense Service.

    Double Entry (Handled automatically by Expense model save):
    DR: Expense Account
    CR: Cash / Bank Account
    """
    amount = Decimal(str(amount)).quantize(TWO_DECIMAL, rounding=ROUND_HALF_UP)
    if amount <= Decimal("0.00"):
        raise ValueError("Expense amount must be greater than zero.")

    expense = Expense.objects.create(
        category=category,
        expense_account=expense_account,
        payment_account=payment_account,
        amount=amount,
        remarks=remarks,
        created_by=created_by
    )

    return expense.journal or expense


# ==========================================================
# 5. CREATE CONTRA VOUCHER SERVICE (CASH/BANK TRANSFERS)
# ==========================================================

@transaction.atomic
def create_contra_voucher(from_account: Account, to_account: Account, amount: Decimal, user=None, remarks=""):
    """
    Contra Voucher for Internal Cash/Bank Transfers.

    Example: Transfer Cash to Bank
    DR: Bank Account (Receiving)
    CR: Cash Account (Sending)
    """
    amount = Decimal(str(amount)).quantize(TWO_DECIMAL, rounding=ROUND_HALF_UP)
    if amount <= Decimal("0.00"):
        raise ValueError("Contra transfer amount must be greater than zero.")

    if from_account == to_account:
        raise ValueError("Source and Destination accounts cannot be the same.")

    contra_journal = Journal.objects.create(
        voucher_type="contra",
        reference_type="contra",
        notes=remarks or f"Transfer from {from_account.name} to {to_account.name}",
        status="posted",
        created_by=user,
        posted_by=user,
        posted_at=timezone.now()
    )

    # DR: Receiving Account
    JournalEntry.objects.create(
        journal=contra_journal,
        account=to_account,
        debit=amount,
        credit=Decimal("0.00"),
        narration=f"Transfer from {from_account.name}",
        created_by=user,
    )

    # CR: Sending Account
    JournalEntry.objects.create(
        journal=contra_journal,
        account=from_account,
        debit=Decimal("0.00"),
        credit=amount,
        narration=f"Transfer to {to_account.name}",
        created_by=user,
    )

    if not contra_journal.is_balanced:
        raise ValidationError("Contra Journal is not balanced.")

    return contra_journal


# ==========================================================
# 6. ACCOUNT OPENING BALANCE JOURNAL SERVICE
# ==========================================================

@transaction.atomic
def create_account_opening_journal(account: Account, created_by=None):
    """
    Creates an Opening Balance Adjustment Journal for newly initialized Accounts.

    For Asset/Expense Accounts:
        DR: Target Account
        CR: Opening Balance Equity Account

    For Liability/Equity/Revenue Accounts:
        DR: Opening Balance Equity Account
        CR: Target Account
    """
    balance = Decimal(str(account.opening_balance or 0)).quantize(TWO_DECIMAL, rounding=ROUND_HALF_UP)
    ZERO = Decimal("0.00")

    if balance <= ZERO:
        return None

    # Prevent Duplicate Opening Journals
    existing = Journal.objects.filter(
        reference_type="manual",
        reference_no=account.account_code,
        notes__icontains="Opening Balance"
    ).first()

    if existing:
        return existing

    # Default Opening Balance Equity Account
    opening_equity_account, _ = Account.objects.get_or_create(
        name="Opening Balance Equity",
        is_default=True,
        defaults={
            "type1": "equity",
            "type2": "capital",
            "status": "active",
        }
    )

    journal = Journal.objects.create(
        voucher_type="journal",
        reference_type="manual",
        reference_no=account.account_code,
        notes=f"Opening Balance : {account.name}",
        status="posted",
        created_by=created_by,
        posted_by=created_by,
        posted_at=timezone.now()
    )

    # Asset or Expense Accounts (Normal Debit Balance)
    if account.type1 in ["asset", "expense"]:
        JournalEntry.objects.create(
            journal=journal,
            account=account,
            debit=balance,
            credit=ZERO,
            narration=f"Opening Balance - {account.name}",
            created_by=created_by,
        )
        JournalEntry.objects.create(
            journal=journal,
            account=opening_equity_account,
            debit=ZERO,
            credit=balance,
            narration="Opening Balance Equity Adjustment",
            created_by=created_by,
        )

    # Liability, Equity, or Revenue Accounts (Normal Credit Balance)
    elif account.type1 in ["liability", "equity", "revenue"]:
        JournalEntry.objects.create(
            journal=journal,
            account=opening_equity_account,
            debit=balance,
            credit=ZERO,
            narration="Opening Balance Equity Adjustment",
            created_by=created_by,
        )
        JournalEntry.objects.create(
            journal=journal,
            account=account,
            debit=ZERO,
            credit=balance,
            narration=f"Opening Balance - {account.name}",
            created_by=created_by,
        )

    if not journal.is_balanced:
        raise ValidationError(f"Opening Journal for {account.name} is not balanced!")

    return journal


# ==========================================================
# BACKWARD COMPATIBILITY ALIASES (পুরনো ইমপোর্ট সাপোর্ট করার জন্য)
# ==========================================================
create_journal = create_sales_voucher
receive_payment_service = receive_customer_payment
make_payment = make_supplier_payment
create_contra = create_contra_voucher
create_receipt = receive_customer_payment