from django.db import models, transaction
from django.utils import timezone
from apps.accounts.models import CustomUser

class Product(models.Model):

    UNIT_CHOICES = [
        ('kg', 'Kg'),
        ('gm', 'gm'),
        ('pcs', 'Pcs'),
        ('ati', 'Ati'),
        ('fana', 'Fana'),
        ('hali', 'Hali'),
    ]

    name = models.CharField(max_length=200)
    price = models.FloatField(help_text="Per unit price (Per Kg for kg/gm)")
    unit = models.CharField(max_length=10, choices=UNIT_CHOICES)
    description = models.TextField(blank=True, null=True)
    image = models.FileField(upload_to='products/', null=True, blank=True)

    @property
    def is_fractional_allowed(self):
        """kg, gm, hali ইউনিটে দশমিক মান এলাউ করা হবে"""
        return self.unit in ['kg', 'gm', 'hali']

    def calculate_price(self, quantity):
        """ইউনিট অনুযায়ী দামের সঠিক হিসাব (গ্রামে থাকলে ১০০০ দিয়ে ভাগ)"""
        if self.unit == 'gm':
            return (quantity / 1000.0) * self.price
        return quantity * self.price

    def __str__(self):
        return self.name

class Order(models.Model):

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('sent_to_uthaan_krishi', 'Sent To Uthaan Krishi'),
        ('supplier_done', 'Uthaan Krishi Reviewed'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
        ('payment_done', 'Payment Done'),
        ('delivery_done', 'Delivery Done'),
    ]

    order_code = models.CharField(max_length=20, unique=True, blank=True)

    user = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='orders'
    )

    assigned_to = models.ForeignKey(
        CustomUser,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='assigned_orders'
    )

    status = models.CharField(
        max_length=30,
        choices=STATUS_CHOICES,
        default='pending'
    )

    is_updated = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    # 🔥 NEW FIELDS
    discount = models.FloatField(default=0)
    packaging_charge = models.FloatField(default=0)

    # NEW: Admin can enable/disable bKash charge
    apply_bkash_charge = models.BooleanField(default=False)

    # =========================
    # ORIGINAL TOTAL
    # =========================
    @property
    def total_price(self):
        return sum(item.total_price() for item in self.items.all())

    # =========================
    # UPDATED TOTAL (ONLY ITEMS)
    # =========================
    @property
    def updated_total_price(self):
        return sum(item.updated_total for item in self.items.all())

    # =========================
    # 🔥 FINAL TOTAL (MAIN)
    # =========================
    @property
    def final_total(self):
        base = self.updated_total_price if self.status == "accepted" else self.total_price

        discount = self.discount if self.discount else 0
        packaging = self.packaging_charge if self.packaging_charge else 0

        return base + packaging - discount

    @property
    def bkash_charge(self):
        if not self.apply_bkash_charge:
            return 0

        return round((self.final_total / 1000) * 18.50, 2)

    @property
    def final_payment(self):
        return round(self.final_total + self.bkash_charge, 2)

    def __str__(self):
        return f"{self.order_code} - {self.user.username}"

    def save(self, *args, **kwargs):

        if not self.order_code:

            with transaction.atomic():

                now = timezone.now()
                month = now.strftime("%m")
                year = now.strftime("%y")

                last_order = Order.objects.filter(
                    created_at__year=now.year,
                    created_at__month=now.month
                ).order_by('-id').first()

                if last_order and last_order.order_code:
                    try:
                        last_serial = int(last_order.order_code.split("-")[0])
                    except:
                        last_serial = 0
                else:
                    last_serial = 0

                serial = str(last_serial + 1).zfill(2)
                self.order_code = f"{serial}-{month}-{year}"

        super().save(*args, **kwargs)

class OrderItem(models.Model):
    is_admin_added = models.BooleanField(default=False)
    is_visible_to_user = models.BooleanField(default=False)

    ITEM_STATUS = [
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
        ('complimentary', 'Complimentary'),
    ]

    order = models.ForeignKey(
        Order,
        related_name='items',
        on_delete=models.CASCADE
    )

    product = models.ForeignKey(Product, on_delete=models.CASCADE)

    quantity = models.FloatField()
    price_at_order_time = models.FloatField(null=True, blank=True)
    remarks = models.CharField(max_length=200, blank=True, null=True)

    updated_quantity = models.FloatField(blank=True, null=True)

    status = models.CharField(
        max_length=20,
        choices=ITEM_STATUS,
        default='pending'
    )

    def total_price(self):
        price = self.price_at_order_time if self.price_at_order_time is not None else self.product.price
        if self.product.unit == 'gm':
            return (self.quantity / 1000.0) * price
        return self.quantity * price

    @property
    def updated_total(self):
        qty = self.updated_quantity if self.updated_quantity is not None else self.quantity
        price = self.price_at_order_time if self.price_at_order_time is not None else self.product.price
        if self.product.unit == 'gm':
            return (qty / 1000.0) * price
        return qty * price

    @property
    def formatted_qty_unit(self):
        qty = self.updated_quantity if (self.order.status == 'accepted' and self.updated_quantity is not None) else self.quantity
        return self.format_quantity(qty, self.product.unit)

    @property
    def formatted_qty_unit_initial(self):
        return self.format_quantity(self.quantity, self.product.unit)

    @property
    def formatted_updated_qty_unit(self):
        """Returns updated_quantity formatted with unit, or '—' if no update."""
        if self.updated_quantity is None:
            return "—"
        return self.format_quantity(self.updated_quantity, self.product.unit)

    @staticmethod
    def format_quantity(qty, unit):
        if qty is None:
            return ""
        if unit == 'gm':
            if qty >= 1000:
                kg = qty / 1000.0
                if kg.is_integer():
                    return f"{int(kg)} kg"
                return f"{round(kg, 2)} kg"
            else:
                if isinstance(qty, float) and qty.is_integer():
                    return f"{int(qty)} gm"
                return f"{qty} gm"
        else:
            unit_str = unit.lower() if unit else ""
            if isinstance(qty, float) and qty.is_integer():
                qty_val = str(int(qty))
            else:
                qty_val = str(round(qty, 2))
            return f"{qty_val} {unit_str}"

    def __str__(self):
        return f"{self.product.name} x {self.quantity}"

    def save(self, *args, **kwargs):

        if self.pk:
            old = OrderItem.objects.filter(pk=self.pk).first()

            if old:
                if (
                    old.quantity != self.quantity or
                    old.updated_quantity != self.updated_quantity or
                    old.remarks != self.remarks or
                    old.status != self.status
                ):
                    self.order.is_updated = True
                    self.order.save(update_fields=['is_updated'])

        super().save(*args, **kwargs)