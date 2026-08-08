# ==========================================================
# IMPORTS
# ==========================================================

from decimal import Decimal

from django.contrib import messages
from django.db import transaction
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, JsonResponse
from django.contrib.auth.decorators import user_passes_test, login_required
from django.core.paginator import Paginator
from django.db.models import Sum, Q
from django.utils import timezone

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4

from apps.products.models import Order, Product
from apps.accounts.models import CustomUser

from .models import (
    Journal,
    JournalEntry,
    JournalItem,
    Account,
    ExpenseCategory,
    PaymentReceipt,
    Expense,
)

from .forms import (
    AccountForm,
    MakePaymentForm,
    VoucherCreateForm,
    JournalEntryFormSet,
)

from .services import (
    receive_customer_payment,
    make_supplier_payment,
    create_expense_voucher,
    create_contra_voucher,
    create_account_opening_journal,
)


# ==========================================================
# ADMIN CHECK PERMISSION
# ==========================================================

def admin_required(user):
    return user.is_authenticated and user.is_superuser


# ==========================================================
# FINANCIAL DASHBOARD
# ==========================================================

@user_passes_test(admin_required)
def financial_dashboard(request):
    """
    Overview of sales, discounts, charges, and account statistics.
    """
    sales_entries = JournalEntry.objects.filter(journal__voucher_type="sales", journal__status="posted")

    total_sale = sales_entries.filter(account__type2="product").aggregate(total=Sum("credit"))["total"] or Decimal("0.00")
    total_discount = sales_entries.filter(account__type2="discount").aggregate(total=Sum("debit"))["total"] or Decimal("0.00")
    total_packaging = sales_entries.filter(account__type2="packaging").aggregate(total=Sum("credit"))["total"] or Decimal("0.00")
    total_bkash = sales_entries.filter(account__type2="bkash_charge").aggregate(total=Sum("credit"))["total"] or Decimal("0.00")

    latest_journals = Journal.objects.select_related("created_by", "order").order_by("-created_at")[:10]

    context = {
        "total_sale": total_sale,
        "total_discount": total_discount,
        "total_packaging": total_packaging,
        "total_bkash": total_bkash,
        "total_orders": Order.objects.count(),
        "total_customers": CustomUser.objects.filter(is_staff=False, is_superuser=False).count(),
        "latest_journals": latest_journals,
    }

    return render(request, "finance/financial_dashboard.html", context)


# ==========================================================
# JOURNAL LIST & DETAIL
# ==========================================================

@user_passes_test(admin_required)
def journal_list(request):
    search = request.GET.get("search", "").strip()

    journals = Journal.objects.select_related("created_by", "order").order_by("-created_at")

    if search:
        journals = journals.filter(
            Q(journal_id__icontains=search)
            | Q(voucher_no__icontains=search)
            | Q(reference_no__icontains=search)
            | Q(order__order_code__icontains=search)
        )

    paginator = Paginator(journals, 20)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(
        request,
        "finance/journal_list.html",
        {
            "page_obj": page_obj,
            "search": search,
        },
    )


@user_passes_test(admin_required)
def journal_detail(request, journal_id):
    journal = get_object_or_404(
        Journal.objects.select_related("created_by", "posted_by", "order"),
        Q(journal_id=journal_id) | Q(voucher_no=journal_id)
    )

    entries = journal.entries.select_related("account").order_by("id")
    items = journal.items.select_related("product")

    subtotal = items.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

    return render(
        request,
        "finance/journal_detail.html",
        {
            "journal": journal,
            "entries": entries,
            "items": items,
            "subtotal": subtotal,
            "total_debit": journal.total_debit,
            "total_credit": journal.total_credit,
        },
    )


# ==========================================================
# CHART OF ACCOUNTS (ACCOUNT CRUD)
# ==========================================================

@login_required
@user_passes_test(admin_required)
def account_list(request):
    accounts = Account.objects.all()

    search = request.GET.get("search", "").strip()
    type1 = request.GET.get("type1", "").strip()
    type2 = request.GET.get("type2", "").strip()
    status = request.GET.get("status", "").strip()

    if search:
        accounts = accounts.filter(
            Q(account_code__icontains=search)
            | Q(name__icontains=search)
            | Q(type1__icontains=search)
            | Q(type2__icontains=search)
        )

    if type1:
        accounts = accounts.filter(type1=type1)
    if type2:
        accounts = accounts.filter(type2=type2)
    if status:
        accounts = accounts.filter(status=status)

    accounts = accounts.order_by("type1", "type2", "name")

    return render(
        request,
        "finance/account_list.html",
        {
            "accounts": accounts,
            "search": search,
            "type1": type1,
            "type2": type2,
            "status": status,
        },
    )


@login_required
@user_passes_test(admin_required)
def account_create(request):
    if request.method == "POST":
        form = AccountForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    account = form.save()
                    create_account_opening_journal(
                        account=account,
                        created_by=request.user,
                    )
                messages.success(request, "Account created successfully.")
                return redirect("account_list")
            except Exception as e:
                messages.error(request, f"Error creating account: {e}")
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = AccountForm()

    return render(
        request,
        "finance/account_form.html",
        {"form": form, "title": "Create Account"},
    )


@login_required
@user_passes_test(admin_required)
def account_update(request, pk):
    account = get_object_or_404(Account, pk=pk)

    if request.method == "POST":
        form = AccountForm(request.POST, instance=account)
        if form.is_valid():
            form.save()
            messages.success(request, "Account updated successfully.")
            return redirect("account_list")
    else:
        form = AccountForm(instance=account)

    return render(
        request,
        "finance/account_form.html",
        {"form": form, "title": "Update Account"},
    )


@login_required
@user_passes_test(admin_required)
def account_delete(request, pk):
    account = get_object_or_404(Account, pk=pk)

    if request.method == "POST":
        account.delete()
        messages.success(request, "Account deleted successfully.")
        return redirect("account_list")

    return render(
        request,
        "finance/account_delete.html",
        {"account": account},
    )


@login_required
@user_passes_test(admin_required)
def account_view(request, pk):
    account = get_object_or_404(Account, pk=pk)
    return redirect("ledger_detail", account_id=account.id)


# ==========================================================
# RECEIVE PAYMENT (ACCOUNT-CENTRIC)
# ==========================================================

@user_passes_test(admin_required)
def receive_payment(request, account_id=None, journal_id=None):
    """
    Receive payment from a Customer Account.
    """
    selected_customer = None
    if account_id:
        selected_customer = Account.objects.filter(id=account_id, type2="customer").first()
    elif journal_id:
        j = Journal.objects.filter(Q(journal_id=journal_id) | Q(voucher_no=journal_id)).first()
        if j and j.customer:
            selected_customer = j.customer

    customer_accounts = Account.objects.filter(type2="customer", status="active").order_by("name")
    cash_bank_accounts = Account.objects.filter(type2__in=["cash", "bank"], status="active").order_by("name")

    if request.method == "POST":
        customer_id = request.POST.get("customer_account") or request.POST.get("customer")
        payment_acc_id = request.POST.get("payment_account")
        amount = request.POST.get("amount")
        remarks = request.POST.get("remarks", "")

        try:
            customer_acc = get_object_or_404(Account, id=customer_id)
            payment_acc = Account.objects.filter(id=payment_acc_id).first() if payment_acc_id else Account.objects.filter(type2="cash", is_default=True).first()

            payment_obj = receive_customer_payment(
                customer_account=customer_acc,
                payment_account=payment_acc,
                amount=Decimal(str(amount)),
                received_by=request.user,
                remarks=remarks,
            )

            messages.success(request, f"Payment of ৳{amount} received successfully.")
            return redirect("ledger_detail", account_id=customer_acc.id)

        except Exception as e:
            messages.error(request, f"Error processing payment: {e}")

    return render(
        request,
        "finance/payment_receive.html",
        {
            "selected_customer": selected_customer,
            "customer_accounts": customer_accounts,
            "cash_bank_accounts": cash_bank_accounts,
        },
    )


# ==========================================================
# MAKE PAYMENT (ACCOUNT-CENTRIC)
# ==========================================================

@user_passes_test(admin_required)
def make_payment_view(request, account_id=None, journal_id=None):
    """
    Make payment to a Supplier or Liability Account.
    """
    selected_party = None
    if account_id:
        selected_party = Account.objects.filter(id=account_id).first()

    party_accounts = Account.objects.filter(
        type1__in=["liability", "expense"],
        status="active"
    ).order_by("name")

    cash_bank_accounts = Account.objects.filter(type2__in=["cash", "bank"], status="active").order_by("name")

    if request.method == "POST":
        party_acc_id = request.POST.get("party_account") or request.POST.get("account")
        payment_acc_id = request.POST.get("payment_account")
        amount = request.POST.get("amount")
        remarks = request.POST.get("remarks", "")

        try:
            party_acc = get_object_or_404(Account, id=party_acc_id)
            payment_acc = Account.objects.filter(id=payment_acc_id).first() if payment_acc_id else Account.objects.filter(type2="cash", is_default=True).first()

            payment_obj = make_supplier_payment(
                party_account=party_acc,
                payment_account=payment_acc,
                amount=Decimal(str(amount)),
                paid_by=request.user,
                remarks=remarks,
            )

            messages.success(request, f"Payment of ৳{amount} to {party_acc.name} recorded successfully.")
            return redirect("ledger_detail", account_id=party_acc.id)

        except Exception as e:
            messages.error(request, f"Error recording payment: {e}")

    return render(
        request,
        "finance/make_payment.html",
        {
            "selected_party": selected_party,
            "party_accounts": party_accounts,
            "cash_bank_accounts": cash_bank_accounts,
        },
    )


# ==========================================================
# CREATE CONTRA VOUCHER
# ==========================================================

@user_passes_test(admin_required)
def create_contra(request):
    cash_bank_accounts = Account.objects.filter(type2__in=["cash", "bank"], status="active").order_by("name")

    if request.method == "POST":
        from_id = request.POST.get("from_account")
        to_id = request.POST.get("to_account")
        amount = request.POST.get("amount")
        remarks = request.POST.get("remarks", "")

        try:
            from_acc = get_object_or_404(Account, id=from_id)
            to_acc = get_object_or_404(Account, id=to_id)

            journal = create_contra_voucher(
                from_account=from_acc,
                to_account=to_acc,
                amount=Decimal(str(amount)),
                user=request.user,
                remarks=remarks,
            )

            messages.success(request, f"Contra Transfer Voucher {journal.voucher_no} created successfully.")
            return redirect("voucher_detail", voucher_no=journal.voucher_no)

        except Exception as e:
            messages.error(request, f"Contra error: {e}")

    return render(
        request,
        "finance/contra_form.html",
        {"accounts": cash_bank_accounts},
    )


# ==========================================================
# LEDGERS & REPORTS
# ==========================================================

@user_passes_test(admin_required)
def ledger_detail(request, account_id):
    account = get_object_or_404(Account, id=account_id)

    entries = JournalEntry.objects.filter(
        account=account,
        journal__status="posted"
    ).select_related("journal", "account").order_by("journal__created_at", "id")

    totals = entries.aggregate(total_debit=Sum("debit"), total_credit=Sum("credit"))
    total_debit = totals["total_debit"] or Decimal("0.00")
    total_credit = totals["total_credit"] or Decimal("0.00")

    # Closing Balance
    if account.type1 in ["asset", "expense"]:
        balance = total_debit - total_credit
    else:
        balance = total_credit - total_debit

    # Calculate Running Balance per entry
    running_balance = Decimal("0.00")
    for entry in entries:
        if account.type1 in ["asset", "expense"]:
            running_balance += (entry.debit - entry.credit)
        else:
            running_balance += (entry.credit - entry.debit)

        entry.running_balance = running_balance

    show_receive_payment = account.type2 in ["customer", "receivable"]
    show_add_payment = account.type2 in ["supplier", "payable"]

    return render(
        request,
        "finance/ledger_detail.html",
        {
            "account": account,
            "entries": entries,
            "total_debit": total_debit,
            "total_credit": total_credit,
            "balance": balance,
            "show_receive_payment": show_receive_payment,
            "show_add_payment": show_add_payment,
        },
    )


@user_passes_test(admin_required)
def cash_ledger(request):
    cash_acc = Account.objects.filter(type2="cash", is_default=True).first()
    if not cash_acc:
        cash_acc, _ = Account.objects.get_or_create(
            name="Cash Account", type1="asset", type2="cash", is_default=True
        )
    return redirect("ledger_detail", account_id=cash_acc.id)


@user_passes_test(admin_required)
def customer_ledger(request):
    customers = Account.objects.filter(type2="customer").order_by("name")
    data = [{"account": acc, "balance": acc.current_balance} for acc in customers]
    return render(request, "finance/customer_ledger.html", {"customers": data})


@user_passes_test(admin_required)
def supplier_ledger(request):
    suppliers = Account.objects.filter(type2="supplier").order_by("name")
    data = [{"account": acc, "balance": acc.current_balance} for acc in suppliers]
    return render(request, "finance/supplier_ledger.html", {"suppliers": data})


@user_passes_test(admin_required)
def bank_ledger(request):
    banks = Account.objects.filter(type2="bank").order_by("name")
    data = [{"account": acc, "balance": acc.current_balance} for acc in banks]
    return render(request, "finance/bank_ledger.html", {"banks": data})


@user_passes_test(admin_required)
def product_ledger(request):
    products = Account.objects.filter(type2="product").order_by("name")
    data = [{"account": acc, "balance": acc.current_balance} for acc in products]
    return render(request, "finance/product_ledger.html", {"products": data})


@user_passes_test(admin_required)
def asset_ledger(request):
    assets = Account.objects.filter(type1="asset").order_by("name")
    data = [{"account": acc, "balance": acc.current_balance} for acc in assets]
    return render(request, "finance/asset_ledger.html", {"assets": data})


@user_passes_test(admin_required)
def liability_ledger(request):
    liabilities = Account.objects.filter(type1="liability").order_by("name")
    data = [{"account": acc, "balance": acc.current_balance} for acc in liabilities]
    return render(request, "finance/liability_ledger.html", {"liabilities": data})


@user_passes_test(admin_required)
def equity_ledger(request):
    equities = Account.objects.filter(type1="equity").order_by("name")
    data = [{"account": acc, "balance": acc.current_balance} for acc in equities]
    return render(request, "finance/equity_ledger.html", {"equities": data})


@user_passes_test(admin_required)
def income_ledger(request):
    incomes = Account.objects.filter(type1="revenue").order_by("name")
    data = [{"account": acc, "balance": acc.current_balance} for acc in incomes]
    return render(request, "finance/income_ledger.html", {"incomes": data})


@user_passes_test(admin_required)
def expense_ledger(request):
    expenses = Account.objects.filter(type1="expense").order_by("name")
    data = [{"account": acc, "balance": acc.current_balance} for acc in expenses]
    return render(request, "finance/expense_ledger.html", {"expenses": data})


@user_passes_test(admin_required)
def receivable_ledger(request):
    receivables = Account.objects.filter(type1="asset", type2="receivable").order_by("name")
    data = [{"account": acc, "balance": acc.current_balance} for acc in receivables]
    return render(request, "finance/receivable_ledger.html", {"receivables": data})


@user_passes_test(admin_required)
def payable_ledger(request):
    payables = Account.objects.filter(type1="liability", type2="payable").order_by("name")
    data = [{"account": acc, "balance": acc.current_balance} for acc in payables]
    return render(request, "finance/payable_ledger.html", {"payables": data})


@user_passes_test(admin_required)
def other_ledger(request):
    others = Account.objects.exclude(type2__in=["customer", "product", "cash", "bank", "supplier"]).order_by("name")
    data = [{"account": acc, "balance": acc.current_balance} for acc in others]
    return render(request, "finance/other_ledger.html", {"others": data})


# ==========================================================
# TRIAL BALANCE REPORT
# ==========================================================

@login_required
@user_passes_test(admin_required)
def trial_balance(request):
    search = request.GET.get("search", "").strip()
    type1 = request.GET.get("type", "").strip()
    from_date = request.GET.get("from_date", "").strip()
    to_date = request.GET.get("to_date", "").strip()

    accounts = Account.objects.all()

    if search:
        accounts = accounts.filter(Q(account_code__icontains=search) | Q(name__icontains=search))
    if type1:
        accounts = accounts.filter(type1=type1)

    accounts = accounts.order_by("account_code")

    rows = []
    total_debit = Decimal("0.00")
    total_credit = Decimal("0.00")

    for account in accounts:
        entries = JournalEntry.objects.filter(account=account, journal__status="posted")
        if from_date:
            entries = entries.filter(entry_date__date__gte=from_date)
        if to_date:
            entries = entries.filter(entry_date__date__lte=to_date)

        totals = entries.aggregate(debit=Sum("debit"), credit=Sum("credit"))
        debit = totals["debit"] or Decimal("0.00")
        credit = totals["credit"] or Decimal("0.00")

        display_debit = Decimal("0.00")
        display_credit = Decimal("0.00")

        if account.type1 in ["asset", "expense"]:
            balance = debit - credit
            if balance >= 0:
                display_debit = balance
            else:
                display_credit = abs(balance)
        else:
            balance = credit - debit
            if balance >= 0:
                display_credit = balance
            else:
                display_debit = abs(balance)

        rows.append({
            "account": account,
            "debit": display_debit,
            "credit": display_credit,
        })

        total_debit += display_debit
        total_credit += display_credit

    return render(
        request,
        "finance/trial_balance.html",
        {
            "rows": rows,
            "total_debit": total_debit,
            "total_credit": total_credit,
            "balanced": total_debit == total_credit,
            "search": search,
            "selected_type": type1,
            "from_date": from_date,
            "to_date": to_date,
        },
    )


# ==========================================================
# MANUAL VOUCHER CREATION / EDIT / POST / CANCEL / DELETE
# ==========================================================

@user_passes_test(admin_required)
def voucher_list(request):
    vouchers = Journal.objects.select_related("created_by", "posted_by", "order").order_by("-created_at")

    search = request.GET.get("search", "").strip()
    voucher_type = request.GET.get("type", "").strip()
    status = request.GET.get("status", "").strip()

    if search:
        vouchers = vouchers.filter(
            Q(voucher_no__icontains=search)
            | Q(journal_id__icontains=search)
            | Q(reference_no__icontains=search)
        )
    if voucher_type:
        vouchers = vouchers.filter(voucher_type=voucher_type)
    if status:
        vouchers = vouchers.filter(status=status)

    paginator = Paginator(vouchers, 20)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(
        request,
        "finance/voucher_list.html",
        {
            "page_obj": page_obj,
            "search": search,
            "voucher_type": voucher_type,
            "status": status,
        },
    )


@user_passes_test(admin_required)
def voucher_detail(request, voucher_no):
    voucher = get_object_or_404(Journal, Q(voucher_no=voucher_no) | Q(journal_id=voucher_no))
    entries = voucher.entries.select_related("account").order_by("id")
    items = voucher.items.select_related("product")

    return render(
        request,
        "finance/voucher_detail.html",
        {
            "voucher": voucher,
            "journal": voucher,
            "entries": entries,
            "items": items,
            "total_debit": voucher.total_debit,
            "total_credit": voucher.total_credit,
        },
    )


@user_passes_test(admin_required)
@transaction.atomic
def voucher_create(request):
    if request.method == "POST":
        form = VoucherCreateForm(request.POST)
        if form.is_valid():
            voucher = form.save(commit=False)
            voucher.created_by = request.user
            voucher.status = "draft"
            voucher.save()

            formset = JournalEntryFormSet(request.POST, instance=voucher)
            if formset.is_valid():
                entries = formset.save(commit=False)
                if not entries:
                    messages.error(request, "At least one journal entry is required.")
                    voucher.delete()
                    return redirect("voucher_create")

                total_dr = sum(e.debit for e in entries)
                total_cr = sum(e.credit for e in entries)

                if total_dr != total_cr or total_dr <= 0:
                    messages.error(request, "Journal entries must be balanced (Debit == Credit > 0).")
                    voucher.delete()
                    return redirect("voucher_create")

                for entry in entries:
                    entry.journal = voucher
                    entry.created_by = request.user
                    entry.save()

                messages.success(request, f"Voucher {voucher.voucher_no} created successfully as draft.")
                return redirect("voucher_detail", voucher_no=voucher.voucher_no)
            voucher.delete()
    else:
        form = VoucherCreateForm()
        formset = JournalEntryFormSet()

    return render(
        request,
        "finance/voucher_form.html",
        {"form": form, "formset": formset, "title": "Create Manual Voucher"},
    )


@user_passes_test(admin_required)
@transaction.atomic
def voucher_edit(request, voucher_no):
    voucher = get_object_or_404(Journal, Q(voucher_no=voucher_no) | Q(journal_id=voucher_no))

    if voucher.status in ["posted", "cancelled"]:
        messages.error(request, "Posted or cancelled voucher cannot be edited.")
        return redirect("voucher_detail", voucher_no=voucher.voucher_no)

    if request.method == "POST":
        form = VoucherCreateForm(request.POST, instance=voucher)
        formset = JournalEntryFormSet(request.POST, instance=voucher)

        if form.is_valid() and formset.is_valid():
            voucher = form.save(commit=False)
            voucher.updated_at = timezone.now()
            voucher.save()

            entries = formset.save(commit=False)
            if not entries:
                messages.error(request, "At least two journal entries are required.")
                return redirect("voucher_edit", voucher_no=voucher.voucher_no)

            total_dr = sum(e.debit for e in entries)
            total_cr = sum(e.credit for e in entries)

            if total_dr != total_cr or total_dr <= 0:
                messages.error(request, "Journal entries must be balanced.")
                return redirect("voucher_edit", voucher_no=voucher.voucher_no)

            JournalEntry.objects.filter(journal=voucher).delete()
            for entry in entries:
                entry.journal = voucher
                entry.created_by = request.user
                entry.save()

            messages.success(request, f"Voucher {voucher.voucher_no} updated successfully.")
            return redirect("voucher_detail", voucher_no=voucher.voucher_no)
    else:
        form = VoucherCreateForm(instance=voucher)
        formset = JournalEntryFormSet(instance=voucher)

    return render(
        request,
        "finance/voucher_form.html",
        {"form": form, "formset": formset, "title": f"Edit Voucher {voucher.voucher_no}"},
    )


@user_passes_test(admin_required)
@transaction.atomic
def voucher_delete(request, voucher_no):
    voucher = get_object_or_404(Journal, Q(voucher_no=voucher_no) | Q(journal_id=voucher_no))

    if voucher.status in ["posted", "cancelled"]:
        messages.error(request, "Posted or cancelled voucher cannot be deleted.")
        return redirect("voucher_detail", voucher_no=voucher.voucher_no)

    if request.method == "POST":
        voucher.delete()
        messages.success(request, "Voucher deleted successfully.")
        return redirect("voucher_list")

    return render(request, "finance/voucher_delete.html", {"voucher": voucher})


@user_passes_test(admin_required)
@transaction.atomic
def voucher_post(request, voucher_no):
    voucher = get_object_or_404(Journal, Q(voucher_no=voucher_no) | Q(journal_id=voucher_no))
    try:
        voucher.post(user=request.user)
        messages.success(request, f"Voucher {voucher.voucher_no} posted successfully.")
    except Exception as e:
        messages.error(request, f"Posting failed: {e}")

    return redirect("voucher_detail", voucher_no=voucher.voucher_no)


@user_passes_test(admin_required)
@transaction.atomic
def voucher_cancel(request, voucher_no):
    voucher = get_object_or_404(Journal, Q(voucher_no=voucher_no) | Q(journal_id=voucher_no))

    if request.method == "POST":
        reason = request.POST.get("reason", "")
        voucher.status = "cancelled"
        voucher.cancelled_by = request.user
        voucher.cancelled_at = timezone.now()
        voucher.cancel_reason = reason
        voucher.save()

        messages.success(request, f"Voucher {voucher.voucher_no} cancelled.")
        return redirect("voucher_detail", voucher_no=voucher.voucher_no)

    return render(request, "finance/voucher_cancel.html", {"voucher": voucher})


# ==========================================================
# PRINT & PDF GENERATION
# ==========================================================

@user_passes_test(admin_required)
def voucher_print(request, voucher_no):
    voucher = get_object_or_404(Journal, Q(voucher_no=voucher_no) | Q(journal_id=voucher_no))
    return render(request, "finance/voucher_print.html", {"voucher": voucher, "journal": voucher})


@user_passes_test(admin_required)
def voucher_pdf(request, voucher_no):
    voucher = get_object_or_404(Journal, Q(voucher_no=voucher_no) | Q(journal_id=voucher_no))
    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{voucher.voucher_no}.pdf"'

    pdf = canvas.Canvas(response, pagesize=A4)
    width, height = A4
    y = height - 50

    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(50, y, "ACCOUNTING VOUCHER")

    y -= 40
    pdf.setFont("Helvetica", 11)
    pdf.drawString(50, y, f"Voucher No: {voucher.voucher_no}")
    y -= 20
    pdf.drawString(50, y, f"Type: {voucher.get_voucher_type_display()}")
    y -= 20
    pdf.drawString(50, y, f"Status: {voucher.status.upper()}")
    y -= 20
    pdf.drawString(50, y, f"Date: {voucher.created_at.strftime('%d-%m-%Y')}")

    y -= 40
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(50, y, "Account")
    pdf.drawString(300, y, "Debit")
    pdf.drawString(420, y, "Credit")

    y -= 20
    pdf.setFont("Helvetica", 10)
    for entry in voucher.entries.all():
        pdf.drawString(50, y, entry.account.name[:35])
        pdf.drawRightString(360, y, str(entry.debit))
        pdf.drawRightString(480, y, str(entry.credit))
        y -= 18
        if y < 80:
            pdf.showPage()
            y = height - 50

    y -= 20
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(50, y, "TOTAL")
    pdf.drawRightString(360, y, str(voucher.total_debit))
    pdf.drawRightString(480, y, str(voucher.total_credit))

    pdf.save()
    return response


def get_account_journals(request, account_id):
    journals = Journal.objects.filter(
        entries__account_id=account_id,
        status="posted"
    ).distinct().order_by("-created_at")

    data = [
        {
            "journal_id": j.journal_id,
            "voucher_no": j.voucher_no,
            "reference_no": j.reference_no,
            "date": j.created_at.strftime("%d-%m-%Y"),
        }
        for j in journals
    ]
    return JsonResponse(data, safe=False)