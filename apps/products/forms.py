from django import forms
from .models import OrderItem


class AdminOrderItemForm(forms.ModelForm):
    class Meta:
        model = OrderItem
        fields = ['product', 'quantity', 'updated_quantity', 'remarks']

    def clean(self):
        cleaned_data = super().clean()
        product = cleaned_data.get('product')
        quantity = cleaned_data.get('quantity')
        updated_quantity = cleaned_data.get('updated_quantity')

        if product:
            # পিস, আঁটি বা ফানা হলে ফ্র্যাকশন এলাউ করা হবে না (পূর্ণসংখ্যা হতে হবে)
            if product.unit in ['pcs', 'ati', 'fana']:
                if quantity is not None and quantity % 1 != 0:
                    self.add_error('quantity', f"Quantity for '{product.get_unit_display()}' must be a whole number.")
                if updated_quantity is not None and updated_quantity % 1 != 0:
                    self.add_error('updated_quantity', f"Updated quantity for '{product.get_unit_display()}' must be a whole number.")

        return cleaned_data


class StaffOrderItemForm(forms.ModelForm):
    class Meta:
        model = OrderItem
        fields = ['remarks']


class OrderItemForm(forms.ModelForm):
    class Meta:
        model = OrderItem
        fields = ['product', 'quantity', 'remarks']

    def clean(self):
        cleaned_data = super().clean()
        product = cleaned_data.get('product')
        quantity = cleaned_data.get('quantity')

        if product and quantity is not None:
            # পিস, আঁটি বা ফানা হলে ফ্র্যাকশন এলাউ করা হবে না
            if product.unit in ['pcs', 'ati', 'fana']:
                if quantity % 1 != 0:
                    self.add_error('quantity', f"Quantity for '{product.get_unit_display()}' must be a whole number.")

        return cleaned_data