from decimal import Decimal, ROUND_HALF_UP
from django.db import models, transaction
from django.utils import timezone
from django.db.models import Sum
from django.core.exceptions import ValidationError
from apps.accounts.models import CustomUser
from apps.products.models import Order, Product

TWO_DECIMAL = Decimal("0.01")
ZERO = Decimal("0.00")

def _q(value):
    if value is None:
        return ZERO
    return Decimal(str(value)).quantize(TWO_DECIMAL, rounding=ROUND_HALF_UP)


# ===========================================
# 1. EXPENSE CATEGORY
# ===========================================

class ExpenseCategory(models.Model):
    name = models.CharField(
        max_length=100,
        unique=True
    )
    description = models.TextField(
        blank=True
    )
    is_active = models.BooleanField(
        default=True
    )

    def __str__(self):
        return self.name

    class Meta:
        verbose_name_plural = "Expense Categories"

# ===========================================
# 2. CHART OF ACCOUNTS (ACCOUNT)
# ===========================================

class Account(models.Model):
    TYPE1_CHOICES = (
        ("asset", "Asset"),
        ("liability", "Liability"),
        ("equity", "Equity"),
        ("revenue", "Revenue"),
        ("expense", "Expense"),
    )

    TYPE2_CHOICES = (
        ("cash", "Cash"),
        ("bank", "Bank"),
        ("customer", "Customer"),
        ("supplier", "Supplier"),
        ("receivable", "Receivable"),
        ("payable", "Payable"),
        ("product", "Product"),
        ("capital", "Capital"),
        ("purchase", "Purchase"),
        ("discount", "Discount"),
        ("packaging", "Packaging Charge"),
        ("bkash_charge", "bKash Charge"),
        ("other", "Other"),
    )

    OPENING_BALANCE_TYPE = (
        ("debit", "Debit"),
        ("credit", "Credit"),
    )

    STATUS_CHOICES = (
        ("active", "Active"),
        ("inactive", "Inactive"),
    )

    account_code = models.CharField(
        max_length=20,
        blank=True,
    )

    name = models.CharField(
        max_length=150
    )

    type1 = models.CharField(
        max_length=20,
        choices=TYPE1_CHOICES,
    )

    type2 = models.CharField(
        max_length=30,
        choices=TYPE2_CHOICES,
        default="other",
    )

    customer = models.OneToOneField(
        CustomUser,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="account"
    )

    product = models.OneToOneField(
        Product,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="account"
    )

    expense_category = models.OneToOneField(
        ExpenseCategory,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="account"
    )

    opening_balance = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    opening_balance_type = models.CharField(
        max_length=10,
        choices=OPENING_BALANCE_TYPE,
        default="debit",
    )

    is_default = models.BooleanField(
        default=False,
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="active",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ["name"]
        indexes = [
            models.Index(fields=["account_code"]),
            models.Index(fields=["name"]),
            models.Index(fields=["type1"]),
            models.Index(fields=["type2"]),
            models.Index(fields=["status"]),
        ]

    @property
    def current_balance(self):
        """
        Calculates current real-time ledger balance considering opening balance
        and all posted journal entries, rounded to 2 decimal places.
        Prevents double-counting if an Opening Balance Journal Voucher already exists.
        """
        posted_entries = self.entries.filter(journal__status="posted")

        # Check if an Opening Balance Journal already exists for this account
        has_op_journal = posted_entries.filter(
            journal__notes__icontains="Opening Balance"
        ).exists()

        totals = posted_entries.aggregate(
            total_debit=Sum("debit"),
            total_credit=Sum("credit")
        )
        t_debit = _q(totals["total_debit"])
        t_credit = _q(totals["total_credit"])

        # If opening balance was already converted to a journal entry, don't double count account.opening_balance
        if has_op_journal:
            op_debit = ZERO
            op_credit = ZERO
        else:
            op_debit = _q(self.opening_balance) if self.opening_balance_type == "debit" else ZERO
            op_credit = _q(self.opening_balance) if self.opening_balance_type == "credit" else ZERO

        net_debit = op_debit + t_debit
        net_credit = op_credit + t_credit

        if self.type1 in ["asset", "expense"]:
            return _q(net_debit - net_credit)
        else:
            return _q(net_credit - net_debit)

    def get_current_balance(self):
        """
        Returns current balance as a normal callable method for Django templates.
        """
        return self.current_balance

    def save(self, *args, **kwargs):
        # Auto Set Opening Balance Type
        if self.type1 in ["asset", "expense"]:
            self.opening_balance_type = "debit"
        elif self.type1 in ["liability", "equity", "revenue"]:
            self.opening_balance_type = "credit"

        # Auto Generate Account Code
        if not self.account_code:
            with transaction.atomic():
                last = (
                    Account.objects
                    .select_for_update()
                    .exclude(account_code="")
                    .order_by("-id")
                    .first()
                )

                if last and last.account_code.startswith("AC"):
                    try:
                        serial = int(last.account_code.replace("AC", "")) + 1
                    except ValueError:
                        serial = 1
                else:
                    serial = 1

                self.account_code = f"AC{serial:06d}"

        # Normalize Status
        if self.status:
            self.status = self.status.lower()

        # Default Opening Balance
        if self.opening_balance is None:
            self.opening_balance = ZERO
        else:
            self.opening_balance = _q(self.opening_balance)

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.account_code} - {self.name}"



# ===========================================
# 3. JOURNAL (VOUCHER HEADER)
# ===========================================

class Journal(models.Model):
    VOUCHER_TYPES = (
        ("sales", "Sales Voucher"),
        ("purchase", "Purchase Voucher"),
        ("payment", "Payment Voucher"),
        ("receipt", "Receipt Voucher"),
        ("expense", "Expense Voucher"),
        ("journal", "Journal Voucher"),
        ("contra", "Contra Voucher"),
    )

    STATUS_CHOICES = (
        ("draft", "Draft"),
        ("posted", "Posted"),
        ("cancelled", "Cancelled"),
    )

    REFERENCE_TYPES = (
        ("invoice", "Invoice"),
        ("purchase", "Purchase"),
        ("payment", "Payment"),
        ("receipt", "Receipt"),
        ("expense", "Expense"),
        ("journal", "Journal"),
        ("contra", "Contra"),
        ("manual", "Manual"),
    )

    journal_id = models.CharField(
        max_length=20,
        blank=True
    )

    voucher_no = models.CharField(
        max_length=30,
        blank=True,
        null=True,
    )

    voucher_type = models.CharField(
        max_length=20,
        choices=VOUCHER_TYPES,
        default="journal",
    )

    reference_type = models.CharField(
        max_length=20,
        choices=REFERENCE_TYPES,
        default="manual",
    )

    reference_no = models.CharField(
        max_length=100,
        blank=True,
        null=True,
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="posted",
    )

    order = models.ForeignKey(
        Order,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="journals"
    )

    customer = models.ForeignKey(
        Account,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="journals"
    )

    notes = models.TextField(
        blank=True,
    )

    created_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_journals",
    )

    posted_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="posted_journals",
    )

    posted_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    approved_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_journals"
    )

    approved_at = models.DateTimeField(
        null=True,
        blank=True
    )

    cancelled_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cancelled_journals"
    )

    cancelled_at = models.DateTimeField(
        null=True,
        blank=True
    )

    cancel_reason = models.TextField(
        blank=True,
        null=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    @property
    def total_debit(self):
        return _q(self.entries.aggregate(total=Sum("debit"))["total"])

    @property
    def total_credit(self):
        return _q(self.entries.aggregate(total=Sum("credit"))["total"])

    @property
    def total_settled_amount(self):
        """Calculates total paid/settled amount against this voucher"""
        return _q(self.payment_settlements.aggregate(total=Sum("amount"))["total"])

    @property
    def is_balanced(self):
        return self.total_debit == self.total_credit and self.total_debit > ZERO

    @property
    def is_draft(self):
        return self.status == "draft"

    @property
    def is_posted(self):
        return self.status == "posted"

    @property
    def is_cancelled(self):
        return self.status == "cancelled"

    def post(self, user=None):
        if self.status == "posted":
            raise ValidationError("This journal is already posted.")

        if not self.is_balanced:
            raise ValidationError(
                f"Unbalanced Journal! Total Debit ({self.total_debit}) must equal Total Credit ({self.total_credit})."
            )

        self.status = "posted"
        self.posted_by = user
        self.posted_at = timezone.now()
        self.save()

    def save(self, *args, **kwargs):
        with transaction.atomic():
            if not self.journal_id:
                last = (
                    Journal.objects
                    .select_for_update()
                    .exclude(journal_id="")
                    .order_by("-id")
                    .first()
                )
                if last and last.journal_id.startswith("JR"):
                    try:
                        serial = int(last.journal_id.replace("JR", "")) + 1
                    except ValueError:
                        serial = 10010001
                else:
                    serial = 10010001

                self.journal_id = f"JR{serial}"

            if not self.voucher_no:
                year = timezone.localtime(timezone.now()).strftime("%y")
                prefix_map = {
                    "sales": "SV",
                    "purchase": "PUV",
                    "payment": "PV",
                    "receipt": "RV",
                    "expense": "EV",
                    "journal": "JV",
                    "contra": "CV",
                }
                prefix = prefix_map.get(self.voucher_type, "JV")

                last_v = (
                    Journal.objects
                    .select_for_update()
                    .filter(voucher_type=self.voucher_type)
                    .order_by("-id")
                    .first()
                )

                serial = 1
                if last_v and last_v.voucher_no:
                    try:
                        parts = last_v.voucher_no.split("-")
                        if len(parts) > 1:
                            serial = int(parts[1][2:]) + 1
                    except (IndexError, ValueError):
                        serial = 1

                self.voucher_no = f"{prefix}-{year}{serial:06d}"

            if self.status == "posted" and self.posted_at is None:
                self.posted_at = timezone.now()

            super().save(*args, **kwargs)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.voucher_no or self.journal_id} ({self.get_voucher_type_display()})"


# ===========================================
# 4. JOURNAL ITEM (PRODUCT INVENTORY ITEMS)
# ===========================================

class JournalItem(models.Model):
    journal = models.ForeignKey(
        Journal,
        on_delete=models.CASCADE,
        related_name="items"
    )

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE
    )

    quantity = models.DecimalField(
        max_digits=12,
        decimal_places=2
    )

    rate = models.DecimalField(
        max_digits=12,
        decimal_places=2
    )

    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2
    )

    remark = models.CharField(
        max_length=200,
        blank=True,
        null=True
    )

    def save(self, *args, **kwargs):
        if self.quantity is not None and self.rate is not None:
            self.amount = _q(self.quantity * self.rate)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.journal.voucher_no} - {self.product.name}"


# ===========================================
# 5. JOURNAL ENTRY (DOUBLE-ENTRY LEDGER LINES)
# ===========================================

class JournalEntry(models.Model):
    journal = models.ForeignKey(
        Journal,
        on_delete=models.CASCADE,
        related_name="entries"
    )

    voucher_no = models.CharField(
        max_length=50,
        null=True,
        blank=True
    )

    voucher_type = models.CharField(
        max_length=20,
        choices=Journal.VOUCHER_TYPES,
        null=True,
        blank=True
    )

    account = models.ForeignKey(
        Account,
        on_delete=models.CASCADE,
        related_name="entries"
    )

    debit = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00")
    )

    credit = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00")
    )

    narration = models.CharField(
        max_length=200,
        blank=True,
        null=True
    )

    created_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="journal_entries"
    )

    entry_date = models.DateTimeField(
        auto_now_add=True
    )

    def clean(self):
        debit_val = _q(self.debit)
        credit_val = _q(self.credit)

        if debit_val > ZERO and credit_val > ZERO:
            raise ValidationError("Debit and Credit cannot both have a value on the same entry line.")

        if debit_val == ZERO and credit_val == ZERO:
            raise ValidationError("Either Debit or Credit amount is required.")

    def save(self, *args, **kwargs):
        self.debit = _q(self.debit)
        self.credit = _q(self.credit)

        if self.journal:
            self.voucher_no = self.journal.voucher_no
            self.voucher_type = self.journal.voucher_type

        self.full_clean()
        super().save(*args, **kwargs)

    class Meta:
        ordering = ["-entry_date", "-id"]

    def __str__(self):
        return f"{self.voucher_no or self.journal.voucher_no} | {self.account.name} | Dr: {self.debit} Cr: {self.credit}"


# ===========================================
# 6. PAYMENT / RECEIPT TRANSACTION
# ===========================================

class PaymentReceipt(models.Model):
    PAYMENT_TYPES = (
        ("receipt", "Receive Payment (Customer)"),
        ("payment", "Make Payment (Supplier/Liability)"),
    )

    payment_type = models.CharField(
        max_length=20,
        choices=PAYMENT_TYPES,
        default="receipt"
    )

    party_account = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="party_payments",
        help_text="Customer or Supplier Account"
    )

    payment_account = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="cash_bank_payments",
        help_text="Cash or Bank Account"
    )

    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2
    )

    remarks = models.CharField(
        max_length=200,
        blank=True
    )

    received_at = models.DateTimeField(
        default=timezone.now
    )

    received_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="received_payments"
    )

    journal = models.OneToOneField(
        Journal,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payment_record",
        help_text="Auto-linked accounting journal voucher"
    )

    class Meta:
        ordering = ["-received_at"]

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        self.amount = _q(self.amount)
        super().save(*args, **kwargs)

        if is_new and not self.journal and self.party_account and self.payment_account:
            with transaction.atomic():
                voucher_type = "receipt" if self.payment_type == "receipt" else "payment"
                narration_text = f"{self.get_payment_type_display()} - {self.party_account.name}. {self.remarks}".strip()

                journal_obj = Journal.objects.create(
                    voucher_type=voucher_type,
                    reference_type="payment" if voucher_type == "payment" else "receipt",
                    reference_no=str(self.id),
                    notes=narration_text,
                    status="posted",
                    created_by=self.received_by,
                    posted_by=self.received_by,
                    posted_at=timezone.now()
                )

                if self.payment_type == "receipt":
                    JournalEntry.objects.create(
                        journal=journal_obj,
                        account=self.payment_account,
                        debit=self.amount,
                        credit=ZERO,
                        narration=f"Cash/Bank Received",
                        created_by=self.received_by
                    )
                    JournalEntry.objects.create(
                        journal=journal_obj,
                        account=self.party_account,
                        debit=ZERO,
                        credit=self.amount,
                        narration=f"Payment from {self.party_account.name}",
                        created_by=self.received_by
                    )
                else:
                    JournalEntry.objects.create(
                        journal=journal_obj,
                        account=self.party_account,
                        debit=self.amount,
                        credit=ZERO,
                        narration=f"Payment to {self.party_account.name}",
                        created_by=self.received_by
                    )
                    JournalEntry.objects.create(
                        journal=journal_obj,
                        account=self.payment_account,
                        debit=ZERO,
                        credit=self.amount,
                        narration=f"Paid via {self.payment_account.name}",
                        created_by=self.received_by
                    )

                self.journal = journal_obj
                super().save(update_fields=["journal"])

    def __str__(self):
        party_name = self.party_account.name if self.party_account else "Unknown"
        return f"{self.get_payment_type_display()} - {party_name} ({self.amount})"


# ===========================================
# 7. EXPENSE TRANSACTION
# ===========================================

class Expense(models.Model):
    category = models.ForeignKey(
        ExpenseCategory,
        on_delete=models.PROTECT,
        related_name="expenses"
    )

    expense_account = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="expense_entries",
        help_text="Expense Ledger Account"
    )

    payment_account = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="expense_payments",
        help_text="Cash or Bank Account used to pay expense"
    )

    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2
    )

    remarks = models.CharField(
        max_length=200,
        blank=True
    )

    expense_date = models.DateTimeField(
        default=timezone.now
    )

    created_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_expenses"
    )

    journal = models.OneToOneField(
        Journal,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="expense_record",
        help_text="Auto-linked accounting journal voucher"
    )

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        self.amount = _q(self.amount)
        super().save(*args, **kwargs)

        if is_new and not self.journal and self.expense_account and self.payment_account:
            with transaction.atomic():
                journal_obj = Journal.objects.create(
                    voucher_type="expense",
                    reference_type="expense",
                    reference_no=str(self.id),
                    notes=f"Expense: {self.category.name}. {self.remarks}".strip(),
                    status="posted",
                    created_by=self.created_by,
                    posted_by=self.created_by,
                    posted_at=timezone.now()
                )

                JournalEntry.objects.create(
                    journal=journal_obj,
                    account=self.expense_account,
                    debit=self.amount,
                    credit=ZERO,
                    narration=f"Expense: {self.category.name}",
                    created_by=self.created_by
                )
                JournalEntry.objects.create(
                    journal=journal_obj,
                    account=self.payment_account,
                    debit=ZERO,
                    credit=self.amount,
                    narration=f"Paid via {self.payment_account.name}",
                    created_by=self.created_by
                )

                self.journal = journal_obj
                super().save(update_fields=["journal"])

    def __str__(self):
        return f"{self.category.name} - {self.amount}"


# ===========================================
# 8. VOUCHER PAYMENT LINE (SETTLEMENT TRACKING)
# ===========================================

class VoucherPaymentLine(models.Model):
    """
    Tracks settlements/payments made specifically against individual vouchers.
    This serves as the foundation for calculation of outstanding voucher balances.
    """
    payment_journal = models.ForeignKey(
        Journal,
        on_delete=models.CASCADE,
        related_name="settlement_lines",
        help_text="The Payment/Receipt Journal (RV/PV)"
    )

    reference_voucher = models.ForeignKey(
        Journal,
        on_delete=models.CASCADE,
        null=True,           # <-- Added null=True & blank=True so Opening Balance payments can be tracked
        blank=True,
        related_name="payment_settlements",
        help_text="The original Sales/Purchase/Expense/Journal voucher being settled (null if Opening Balance)"
    )

    account = models.ForeignKey(
        Account,
        on_delete=models.CASCADE,
        related_name="voucher_payment_lines",
        help_text="Customer or Supplier account"
    )

    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def save(self, *args, **kwargs):
        self.amount = _q(self.amount)
        super().save(*args, **kwargs)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Voucher Payment Line"
        verbose_name_plural = "Voucher Payment Lines"

    def __str__(self):
        ref = self.reference_voucher.voucher_no if self.reference_voucher else "OPENING-BALANCE"
        return f"{self.payment_journal.voucher_no} -> {ref} ({self.amount})"