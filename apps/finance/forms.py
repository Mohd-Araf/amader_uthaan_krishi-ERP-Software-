from decimal import Decimal

from django import forms
from django.forms import inlineformset_factory
from django.db.models import Q

from .models import (
    Account,
    Journal,
    JournalEntry,
    Expense,
    ExpenseCategory,
    PaymentReceipt,
)


# ==========================================
# 1. Payment Form (Supplier / Payable / Expense)
# ==========================================

class MakePaymentForm(forms.Form):
    account = forms.ModelChoiceField(
        queryset=Account.objects.none(),
        widget=forms.Select(attrs={"class": "form-select"}),
        label="Pay To Account",
        required=True
    )

    payment_account = forms.ModelChoiceField(
        queryset=Account.objects.none(),
        widget=forms.Select(attrs={"class": "form-select"}),
        label="Pay From (Cash/Bank)",
        required=False
    )

    amount = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        widget=forms.NumberInput(
            attrs={
                "class": "form-control",
                "step": "0.01",
                "placeholder": "Enter Payment Amount",
            }
        ),
        label="Payment Amount",
        required=True
    )

    remarks = forms.CharField(
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Remarks (Optional)",
            }
        ),
        label="Remarks"
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["account"].queryset = (
            Account.objects.filter(status="active")
            .filter(
                Q(type1="expense")
                | Q(type1="liability")
                | Q(type2="supplier")
                | Q(type2="payable")
            )
            .order_by("name")
        )
        self.fields["account"].empty_label = "Select Supplier / Liability / Payable / Expense Account"

        self.fields["payment_account"].queryset = (
            Account.objects.filter(status="active", type2__in=["cash", "bank"]).order_by("name")
        )
        self.fields["payment_account"].empty_label = "Select Cash or Bank Account"


# ==========================================
# 2. Receive Payment Form
# ==========================================

class ReceivePaymentForm(forms.Form):
    customer_account = forms.ModelChoiceField(
        queryset=Account.objects.filter(status="active", type2="customer").order_by("name"),
        widget=forms.Select(attrs={"class": "form-select"}),
        label="Customer Account",
        required=True
    )

    payment_account = forms.ModelChoiceField(
        queryset=Account.objects.filter(status="active", type2__in=["cash", "bank"]).order_by("name"),
        widget=forms.Select(attrs={"class": "form-select"}),
        label="Deposit To (Cash/Bank)",
        required=True
    )

    amount = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        widget=forms.NumberInput(
            attrs={
                "class": "form-control",
                "step": "0.01",
                "placeholder": "Enter Received Amount",
            }
        ),
        required=True
    )

    remarks = forms.CharField(
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Remarks (Optional)",
            }
        )
    )


# ==========================================
# 3. Expense Category Form
# ==========================================

class ExpenseCategoryForm(forms.ModelForm):
    class Meta:
        model = ExpenseCategory
        fields = (
            "name",
            "description",
            "is_active",
        )
        widgets = {
            "name": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Category Name",
                }
            ),
            "description": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "Description",
                }
            ),
            "is_active": forms.CheckboxInput(
                attrs={
                    "class": "form-check-input",
                }
            ),
        }


# ==========================================
# 4. Account Form (Chart of Accounts)
# ==========================================

class AccountForm(forms.ModelForm):
    class Meta:
        model = Account
        fields = [
            "name",
            "type1",
            "type2",
            "opening_balance",

            "status",
        ]
        widgets = {
            "name": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Account Name",
                }
            ),
            "type1": forms.Select(
                attrs={
                    "class": "form-select",
                }
            ),
            "type2": forms.Select(
                attrs={
                    "class": "form-select",
                }
            ),
            "opening_balance": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "step": "0.01",
                }
            ),
            "opening_balance_type": forms.Select(
                attrs={
                    "class": "form-select",
                }
            ),
            "status": forms.Select(
                attrs={
                    "class": "form-select",
                }
            ),
        }


# ==========================================
# 5. Voucher Header Form
# ==========================================

class VoucherCreateForm(forms.ModelForm):
    class Meta:
        model = Journal
        fields = [
            "voucher_type",
            "reference_type",
            "reference_no",
            "notes",
        ]
        widgets = {
            "voucher_type": forms.Select(
                attrs={
                    "class": "form-select",
                }
            ),
            "reference_type": forms.Select(
                attrs={
                    "class": "form-select",
                }
            ),
            "reference_no": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Reference No",
                }
            ),
            "notes": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "Narration / Description",
                }
            ),
        }


# ==========================================
# 6. Voucher Entry Form
# ==========================================

class JournalEntryForm(forms.ModelForm):
    class Meta:
        model = JournalEntry
        fields = [
            "account",
            "debit",
            "credit",
            "narration",
        ]
        widgets = {
            "account": forms.Select(
                attrs={
                    "class": "form-select"
                }
            ),
            "debit": forms.NumberInput(
                attrs={
                    "class": "form-control debit-input",
                    "step": "0.01",
                    "placeholder": "Debit Amount",
                }
            ),
            "credit": forms.NumberInput(
                attrs={
                    "class": "form-control credit-input",
                    "step": "0.01",
                    "placeholder": "Credit Amount",
                }
            ),
            "narration": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Narration",
                }
            ),
        }

    def clean(self):
        cleaned_data = super().clean()
        debit = cleaned_data.get("debit") or Decimal("0.00")
        credit = cleaned_data.get("credit") or Decimal("0.00")

        if debit > 0 and credit > 0:
            raise forms.ValidationError("Debit and Credit cannot both contain a value on the same line.")

        if debit == 0 and credit == 0:
            raise forms.ValidationError("Enter either Debit or Credit amount.")

        return cleaned_data


# ==========================================
# 7. Voucher FormSet Validation
# ==========================================

class BaseJournalEntryFormSet(forms.BaseInlineFormSet):
    def clean(self):
        super().clean()
        total_debit = Decimal("0.00")
        total_credit = Decimal("0.00")
        entry_count = 0

        for form in self.forms:
            if not hasattr(form, "cleaned_data"):
                continue

            if form.cleaned_data.get("DELETE"):
                continue

            account = form.cleaned_data.get("account")
            debit = form.cleaned_data.get("debit") or Decimal("0.00")
            credit = form.cleaned_data.get("credit") or Decimal("0.00")

            if account:
                entry_count += 1

            total_debit += debit
            total_credit += credit

        if entry_count < 2:
            raise forms.ValidationError("At least two journal entries are required for a double entry voucher.")

        if total_debit <= 0:
            raise forms.ValidationError("Debit amount must be greater than zero.")

        if total_debit != total_credit:
            raise forms.ValidationError(
                f"Journal is not balanced! Total Debit (৳{total_debit}) must equal Total Credit (৳{total_credit}).")


JournalEntryFormSet = inlineformset_factory(
    Journal,
    JournalEntry,
    form=JournalEntryForm,
    formset=BaseJournalEntryFormSet,
    extra=2,
    can_delete=True,
    fields=[
        "account",
        "debit",
        "credit",
        "narration",
    ]
)