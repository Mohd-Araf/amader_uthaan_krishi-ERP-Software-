from django import forms
from .models import OrderItem


class AdminOrderItemForm(forms.ModelForm):
    class Meta:
        model = OrderItem
        fields = ['product', 'quantity', 'updated_quantity', 'remarks']

class StaffOrderItemForm(forms.ModelForm):
    class Meta:
        model = OrderItem
        fields = ['remarks']

class OrderItemForm(forms.ModelForm):
    class Meta:
        model = OrderItem
        fields = ['product', 'quantity', 'remarks']