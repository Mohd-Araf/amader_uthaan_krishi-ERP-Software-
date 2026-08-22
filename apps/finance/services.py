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
    VoucherPaymentLine,
)

TWO_DECIMAL = Decimal("0.01")
ZERO = Decimal("0.00")


# ==========================================================
# OUTSTANDING VOUCHERS HELPER SERVICE
# ==========================================================

def get_outstanding_vouchers(account: Account):
    """
    Returns a list of all posted vouchers (including Opening Balance if any)
    for a specific Customer or Supplier account that still have an unpaid balance.
    Prevents duplicate virtual Opening Balance vouchers if a real Journal Voucher exists.
    """
    if not account:
        return []

    results = []

    is_customer = account.type2 in ["customer", "receivable"] or account.type1 == "asset"
    is_supplier = account.type2 in ["supplier", "payable"] or account.type1 in ["liability", "expense"]

    # ----------------------------------------------------------
    # Check if a real Journal Voucher for Opening Balance exists
    # ----------------------------------------------------------
    has_op_journal = JournalEntry.objects.filter(
        account=account,
        journal__status="posted",
        journal__notes__icontains="Opening Balance"
    ).exists() or Journal.objects.filter(
        reference_no=account.account_code,
        notes__icontains="Opening Balance",
        status="posted"
    ).exists()

    # ----------------------------------------------------------
    # 1. OPENING BALANCE VOUCHER (ডাইরেক্ট Opening Balance থাকলে এবং আসল জার্নাল না থাকলে)
    # ----------------------------------------------------------
    op_bal = account.opening_balance or ZERO
    if op_bal > ZERO and not has_op_journal:
        op_settled = VoucherPaymentLine.objects.filter(
            account=account,
            reference_voucher__isnull=True
        ).aggregate(s=Sum("amount"))["s"] or ZERO

        op_outstanding = (op_bal - op_settled).quantize(TWO_DECIMAL, rounding=ROUND_HALF_UP)

        if op_outstanding > ZERO:
            results.append({
                "journal": None,
                "voucher_no": "OPENING-BALANCE",
                "voucher_type": "Opening Balance",
                "original_amount": op_bal,
                "paid_amount": op_settled,
                "settled_amount": op_settled,
                "outstanding": op_outstanding,
                "outstanding_amount": op_outstanding,
                "is_opening": True,
            })

    # ----------------------------------------------------------
    # 2. JOURNAL VOUCHERS (Sales, Purchase, JV, EV)
    # ----------------------------------------------------------
    if is_customer:
        entries = JournalEntry.objects.filter(
            account=account,
            debit__gt=ZERO,
            journal__status="posted"
        ).exclude(journal__voucher_type__in=["receipt", "payment", "contra"]).select_related("journal")

        # Unlinked receipt credits
        total_receipt_credits = JournalEntry.objects.filter(
            account=account,
            credit__gt=ZERO,
            journal__status="posted",
            journal__voucher_type__in=["receipt", "payment", "contra"]
        ).aggregate(total=Sum("credit"))["total"] or ZERO

        total_vpl_credits = VoucherPaymentLine.objects.filter(
            account=account
        ).aggregate(total=Sum("amount"))["total"] or ZERO

        unlinked_pool = max(ZERO, total_receipt_credits - total_vpl_credits)

        for entry in entries:
            journal = entry.journal
            original_amount = entry.debit

            paid_via_vpl = VoucherPaymentLine.objects.filter(
                reference_voucher=journal,
                account=account
            ).aggregate(total=Sum("amount"))["total"] or ZERO

            gap = original_amount - paid_via_vpl
            additional_paid = min(unlinked_pool, gap)
            unlinked_pool = max(ZERO, unlinked_pool - additional_paid)

            paid_amount = paid_via_vpl + additional_paid
            outstanding = (original_amount - paid_amount).quantize(TWO_DECIMAL, rounding=ROUND_HALF_UP)

            if outstanding > ZERO:
                results.append({
                    "journal": journal,
                    "voucher_no": journal.voucher_no,
                    "voucher_type": journal.get_voucher_type_display(),
                    "original_amount": original_amount,
                    "paid_amount": paid_amount,
                    "settled_amount": paid_amount,
                    "outstanding": outstanding,
                    "outstanding_amount": outstanding,
                    "is_opening": False,
                })

    elif is_supplier:
        entries = JournalEntry.objects.filter(
            account=account,
            credit__gt=ZERO,
            journal__status="posted"
        ).exclude(journal__voucher_type__in=["receipt", "payment", "contra"]).select_related("journal")

        # Unlinked payment debits
        total_payment_debits = JournalEntry.objects.filter(
            account=account,
            debit__gt=ZERO,
            journal__status="posted",
            journal__voucher_type__in=["receipt", "payment", "contra"]
        ).aggregate(total=Sum("debit"))["total"] or ZERO

        total_vpl_debits = VoucherPaymentLine.objects.filter(
            account=account
        ).aggregate(total=Sum("amount"))["total"] or ZERO

        unlinked_pool = max(ZERO, total_payment_debits - total_vpl_debits)

        for entry in entries:
            journal = entry.journal
            original_amount = entry.credit

            paid_via_vpl = VoucherPaymentLine.objects.filter(
                reference_voucher=journal,
                account=account
            ).aggregate(total=Sum("amount"))["total"] or ZERO

            gap = original_amount - paid_via_vpl
            additional_paid = min(unlinked_pool, gap)
            unlinked_pool = max(ZERO, unlinked_pool - additional_paid)

            paid_amount = paid_via_vpl + additional_paid
            outstanding = (original_amount - paid_amount).quantize(TWO_DECIMAL, rounding=ROUND_HALF_UP)

            if outstanding > ZERO:
                results.append({
                    "journal": journal,
                    "voucher_no": journal.voucher_no,
                    "voucher_type": journal.get_voucher_type_display(),
                    "original_amount": original_amount,
                    "paid_amount": paid_amount,
                    "settled_amount": paid_amount,
                    "outstanding": outstanding,
                    "outstanding_amount": outstanding,
                    "is_opening": False,
                })

    results.sort(key=lambda x: x["journal"].created_at if x["journal"] else timezone.now())
    return results


# ==========================================================
# 1. CREATE / SYNC SALES VOUCHER AUTOMATICALLY FOR ORDERS
# ==========================================================

@transaction.atomic
def create_sales_voucher(order: Order, created_by=None):
    """
    Sales Voucher Auto Generator for Orders with Discount, Packaging, bKash & Item Status handling.
    """
    # Fetch or recreate Journal Voucher Header
    journal = order.journals.filter(voucher_type="sales").first()
    if journal:
        journal.entries.all().delete()
        journal.items.all().delete()
        journal.notes = f"Sales Invoice for Order #{order.order_code}"
        journal.save()
    else:
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

    # Customer Account
    customer_account, _ = Account.objects.get_or_create(
        customer=order.user,
        defaults={
            "name": f"{order.user.username or order.user.email}",
            "type1": "asset",
            "type2": "customer",
            "status": "active",
        },
    )

    # Smart Account Match for System Ledgers
    discount_account = Account.objects.filter(type2="discount").first() or Account.objects.filter(
        name__icontains="Discount").first()
    if not discount_account:
        discount_account = Account.objects.create(
            name="Sales Discount", type1="expense", type2="discount", is_default=True, status="active"
        )

    packaging_account = Account.objects.filter(type2="packaging").first() or Account.objects.filter(
        name__icontains="Packaging").first()
    if not packaging_account:
        packaging_account = Account.objects.create(
            name="Packaging Charge Revenue", type1="revenue", type2="packaging", is_default=True, status="active"
        )

    bkash_account = Account.objects.filter(type2="bkash_charge").first() or Account.objects.filter(
        name__icontains="bKash").first()
    if not bkash_account:
        bkash_account = Account.objects.create(
            name="bKash Charge Revenue", type1="revenue", type2="bkash_charge", is_default=True, status="active"
        )

    # STEP 1: Process Order Items (CR side)
    items = OrderItem.objects.filter(order=order).select_related("product")
    item_entries = []
    total_item_amount = ZERO

    for item in items:
        if item.status == "rejected":
            continue

        qty = Decimal(str(
            item.updated_quantity if item.updated_quantity is not None else item.quantity
        ))

        if item.status == "complimentary":
            rate = ZERO
            amount = ZERO
        else:
            rate = Decimal(str(
                item.price_at_order_time if item.price_at_order_time is not None else item.product.price
            )).quantize(TWO_DECIMAL, rounding=ROUND_HALF_UP)
            amount = (qty * rate).quantize(TWO_DECIMAL, rounding=ROUND_HALF_UP)

        product_account, _ = Account.objects.get_or_create(
            product=item.product,
            defaults={
                "name": f"Sales Revenue - {item.product.name}",
                "type1": "revenue",
                "type2": "product",
                "status": "active",
            },
        )

        item_entries.append({
            "item": item,
            "product_account": product_account,
            "qty": qty,
            "rate": rate,
            "amount": amount,
            "is_complimentary": (item.status == "complimentary"),
        })

        total_item_amount += amount

    # STEP 2: Calculate Charges
    discount = Decimal(str(getattr(order, "discount", 0) or 0)).quantize(TWO_DECIMAL, rounding=ROUND_HALF_UP)
    packaging_charge = Decimal(str(getattr(order, "packaging_charge", 0) or 0)).quantize(TWO_DECIMAL, rounding=ROUND_HALF_UP)

    temp_final_total = total_item_amount + packaging_charge - discount
    if temp_final_total < ZERO:
        temp_final_total = ZERO

    bkash_enabled = getattr(order, "apply_bkash_charge", False) or getattr(order, "is_bkash_charge_added", False)

    if bkash_enabled:
        bkash_charge = (temp_final_total * Decimal("18.50") / Decimal("1000")).quantize(TWO_DECIMAL, rounding=ROUND_HALF_UP)
    else:
        bkash_charge = ZERO

    actual_receivable = (total_item_amount + packaging_charge + bkash_charge - discount).quantize(
        TWO_DECIMAL, rounding=ROUND_HALF_UP
    )
    if actual_receivable < ZERO:
        actual_receivable = ZERO

    # STEP 3: Create DR Entries
    JournalEntry.objects.create(
        journal=journal,
        account=customer_account,
        debit=actual_receivable,
        credit=ZERO,
        narration=f"Invoice #{order.order_code}",
        created_by=created_by,
    )

    if discount > ZERO:
        JournalEntry.objects.create(
            journal=journal,
            account=discount_account,
            debit=discount,
            credit=ZERO,
            narration=f"Sales Discount for Order #{order.order_code}",
            created_by=created_by,
        )

    # STEP 4: Create CR Entries
    if packaging_charge > ZERO:
        JournalEntry.objects.create(
            journal=journal,
            account=packaging_account,
            debit=ZERO,
            credit=packaging_charge,
            narration=f"Packaging Charge for Order #{order.order_code}",
            created_by=created_by,
        )

    if bkash_charge > ZERO:
        JournalEntry.objects.create(
            journal=journal,
            account=bkash_account,
            debit=ZERO,
            credit=bkash_charge,
            narration=f"bKash Charge for Order #{order.order_code}",
            created_by=created_by,
        )

    for entry_data in item_entries:
        item = entry_data["item"]
        amt = entry_data["amount"]
        is_comp = entry_data["is_complimentary"]

        remark_txt = item.remarks or f"Sold {item.product.name}"
        if is_comp:
            remark_txt = f"Complimentary Item: {item.product.name}"

        JournalItem.objects.create(
            journal=journal,
            product=item.product,
            quantity=entry_data["qty"],
            rate=entry_data["rate"],
            amount=amt,
            remark=remark_txt,
        )

        if amt > ZERO:
            JournalEntry.objects.create(
                journal=journal,
                account=entry_data["product_account"],
                debit=ZERO,
                credit=amt,
                narration=f"Sold {item.product.name} (Qty: {entry_data['qty']})",
                created_by=created_by,
            )

    if not journal.is_balanced:
        raise ValidationError(
            f"Sales Journal for Order #{order.order_code} is not balanced! "
            f"Total Debit: {journal.total_debit}, Total Credit: {journal.total_credit}"
        )

    return journal


# ==========================================================
# 2. VOUCHER-WISE RECEIVE CUSTOMER PAYMENT SERVICE
# ==========================================================

@transaction.atomic
def receive_customer_payment_voucher_wise(customer_account: Account, payment_account: Account, payment_lines: list,
                                          received_by=None, remarks=""):
    valid_lines = []
    total_received = ZERO

    for line in payment_lines:
        v_id = line.get("voucher_id")
        amt = Decimal(str(line.get("amount") or 0)).quantize(TWO_DECIMAL, rounding=ROUND_HALF_UP)
        if amt > ZERO:
            if str(v_id).upper() == "OPENING-BALANCE" or line.get("is_opening"):
                valid_lines.append({
                    "ref_voucher": None,
                    "amount": amt,
                    "is_opening": True
                })
                total_received += amt
            elif v_id:
                ref_voucher = Journal.objects.filter(id=v_id, status="posted").first()
                if ref_voucher:
                    valid_lines.append({
                        "ref_voucher": ref_voucher,
                        "amount": amt,
                        "is_opening": False
                    })
                    total_received += amt

    if total_received <= ZERO or not valid_lines:
        raise ValueError("Please enter a valid amount greater than zero for at least one voucher.")

    if not payment_account:
        payment_account, _ = Account.objects.get_or_create(
            type2="cash",
            is_default=True,
            defaults={"name": "Cash", "type1": "asset", "status": "active"}
        )

    journal_obj = Journal.objects.create(
        voucher_type="receipt",
        reference_type="receipt",
        customer=customer_account,
        notes=f"Payment Received from {customer_account.name}. {remarks}".strip(),
        status="posted",
        created_by=received_by,
        posted_by=received_by,
        posted_at=timezone.now()
    )

    JournalEntry.objects.create(
        journal=journal_obj,
        account=payment_account,
        debit=total_received,
        credit=ZERO,
        narration=f"Cash/Bank Received from {customer_account.name}",
        created_by=received_by
    )

    for line in valid_lines:
        ref_v = line["ref_voucher"]
        amt = line["amount"]
        v_no = ref_v.voucher_no if ref_v else "OPENING-BALANCE"

        JournalEntry.objects.create(
            journal=journal_obj,
            account=customer_account,
            debit=ZERO,
            credit=amt,
            narration=f"Received against Voucher #{v_no}",
            created_by=received_by
        )

        VoucherPaymentLine.objects.create(
            payment_journal=journal_obj,
            reference_voucher=ref_v,
            account=customer_account,
            amount=amt
        )

    PaymentReceipt.objects.create(
        payment_type="receipt",
        party_account=customer_account,
        payment_account=payment_account,
        amount=total_received,
        remarks=remarks,
        received_by=received_by,
        journal=journal_obj
    )

    if not journal_obj.is_balanced:
        raise ValidationError("Receipt Journal is not balanced!")

    return journal_obj


# ==========================================================
# 3. VOUCHER-WISE MAKE SUPPLIER PAYMENT SERVICE
# ==========================================================

@transaction.atomic
def make_supplier_payment_voucher_wise(party_account: Account, payment_account: Account, payment_lines: list,
                                       paid_by=None, remarks=""):
    valid_lines = []
    total_paid = ZERO

    for line in payment_lines:
        v_id = line.get("voucher_id")
        amt = Decimal(str(line.get("amount") or 0)).quantize(TWO_DECIMAL, rounding=ROUND_HALF_UP)
        if amt > ZERO:
            if str(v_id).upper() == "OPENING-BALANCE" or line.get("is_opening"):
                valid_lines.append({
                    "ref_voucher": None,
                    "amount": amt,
                    "is_opening": True
                })
                total_paid += amt
            elif v_id:
                ref_voucher = Journal.objects.filter(id=v_id, status="posted").first()
                if ref_voucher:
                    valid_lines.append({
                        "ref_voucher": ref_voucher,
                        "amount": amt,
                        "is_opening": False
                    })
                    total_paid += amt

    if total_paid <= ZERO or not valid_lines:
        raise ValueError("Please enter a valid payment amount greater than zero for at least one voucher.")

    if not payment_account:
        payment_account, _ = Account.objects.get_or_create(
            type1="asset",
            type2="cash",
            is_default=True,
            defaults={"name": "Cash", "status": "active"}
        )

    journal_obj = Journal.objects.create(
        voucher_type="payment",
        reference_type="payment",
        notes=f"Payment made to {party_account.name}. {remarks}".strip(),
        status="posted",
        created_by=paid_by,
        posted_by=paid_by,
        posted_at=timezone.now()
    )

    for line in valid_lines:
        ref_v = line["ref_voucher"]
        amt = line["amount"]
        v_no = ref_v.voucher_no if ref_v else "OPENING-BALANCE"

        JournalEntry.objects.create(
            journal=journal_obj,
            account=party_account,
            debit=amt,
            credit=ZERO,
            narration=f"Payment against Voucher #{v_no}",
            created_by=paid_by
        )

        VoucherPaymentLine.objects.create(
            payment_journal=journal_obj,
            reference_voucher=ref_v,
            account=party_account,
            amount=amt
        )

    JournalEntry.objects.create(
        journal=journal_obj,
        account=payment_account,
        debit=ZERO,
        credit=total_paid,
        narration=f"Paid via {payment_account.name}",
        created_by=paid_by
    )

    PaymentReceipt.objects.create(
        payment_type="payment",
        party_account=party_account,
        payment_account=payment_account,
        amount=total_paid,
        remarks=remarks,
        received_by=paid_by,
        journal=journal_obj
    )

    if not journal_obj.is_balanced:
        raise ValidationError("Payment Journal is not balanced!")

    return journal_obj


# ==========================================================
# BACKWARD COMPATIBLE SINGLE RECEIVE / PAYMENT SERVICES
# ==========================================================

@transaction.atomic
def receive_customer_payment(customer_account: Account, payment_account: Account = None,
                             amount: Decimal = Decimal("0.00"), received_by=None, remarks="", journal=None):
    amount = Decimal(str(amount)).quantize(TWO_DECIMAL, rounding=ROUND_HALF_UP)
    if amount <= ZERO:
        raise ValueError("Received amount must be greater than zero.")

    if not payment_account:
        payment_account, _ = Account.objects.get_or_create(
            type2="cash",
            is_default=True,
            defaults={"name": "Cash", "type1": "asset", "status": "active"}
        )

    if journal and not customer_account:
        customer_account = journal.customer

    payment = PaymentReceipt.objects.create(
        payment_type="receipt",
        party_account=customer_account,
        payment_account=payment_account,
        amount=amount,
        remarks=remarks,
        received_by=received_by
    )

    return payment.journal or payment


@transaction.atomic
def make_supplier_payment(account: Account = None, payment_account: Account = None, amount: Decimal = Decimal("0.00"),
                          created_by=None, remarks="", journal=None, paid_by=None, party_account=None):
    target_party = party_account or account
    user = paid_by or created_by

    amount = Decimal(str(amount)).quantize(TWO_DECIMAL, rounding=ROUND_HALF_UP)
    if amount <= ZERO:
        raise ValueError("Payment amount must be greater than zero.")

    if not payment_account:
        payment_account, _ = Account.objects.get_or_create(
            type1="asset",
            type2="cash",
            is_default=True,
            defaults={"name": "Cash", "status": "active"}
        )

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
def create_expense_voucher(category: ExpenseCategory, expense_account: Account, payment_account: Account,
                           amount: Decimal, created_by=None, remarks=""):
    amount = Decimal(str(amount)).quantize(TWO_DECIMAL, rounding=ROUND_HALF_UP)
    if amount <= ZERO:
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
    amount = Decimal(str(amount)).quantize(TWO_DECIMAL, rounding=ROUND_HALF_UP)
    if amount <= ZERO:
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

    JournalEntry.objects.create(
        journal=contra_journal,
        account=to_account,
        debit=amount,
        credit=ZERO,
        narration=f"Transfer from {from_account.name}",
        created_by=user,
    )

    JournalEntry.objects.create(
        journal=contra_journal,
        account=from_account,
        debit=ZERO,
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
    balance = Decimal(str(account.opening_balance or 0)).quantize(TWO_DECIMAL, rounding=ROUND_HALF_UP)

    if balance <= ZERO:
        return None

    existing = Journal.objects.filter(
        reference_type="manual",
        reference_no=account.account_code,
        notes__icontains="Opening Balance"
    ).first()

    if existing:
        return existing

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
# BACKWARD COMPATIBILITY ALIASES
# ==========================================================
create_journal = create_sales_voucher
receive_payment_service = receive_customer_payment
make_payment = make_supplier_payment
create_contra = create_contra_voucher
create_receipt = receive_customer_payment