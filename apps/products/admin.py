from django.contrib import admin
from .models import Product, Order, OrderItem


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0

    fields = (
        'product',
        'quantity',
        'updated_quantity',
        'unit_price_display',
        'total_price_display',
        'updated_total_display',
        'remarks',
        'status',
    )

    readonly_fields = (
        'unit_price_display',
        'total_price_display',
        'updated_total_display',
    )

    def unit_price_display(self, obj):
        if obj.product:
            return f"{obj.product.price} ৳ / {obj.product.get_unit_display()}"
        return "0 ৳"
    unit_price_display.short_description = "Unit Price"

    def total_price_display(self, obj):
        return f"{round(obj.total_price(), 2)} ৳"
    total_price_display.short_description = "Total"

    def updated_total_display(self, obj):
        return f"{round(obj.updated_total, 2)} ৳"
    updated_total_display.short_description = "Updated Total"


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):

    list_display = (
        'id',
        'order_code',
        'user',
        'assigned_to',
        'status',
        'total_price_display',
        'updated_total_display',
        'created_at'
    )

    list_filter = (
        'status',
        'created_at'
    )

    # Added user__user_id so admins can search orders by User ID in Admin Panel
    search_fields = (
        'order_code',
        'user__username',
        'user__email',
        'user__user_id',
    )

    inlines = [OrderItemInline]

    def total_price_display(self, obj):
        return f"{round(obj.total_price, 2)} ৳"
    total_price_display.short_description = "Total"

    def updated_total_display(self, obj):
        return f"{round(obj.updated_total_price, 2)} ৳"
    updated_total_display.short_description = "Updated Total"


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'price', 'unit', 'image')
    fields = ('name', 'price', 'unit', 'description', 'image')