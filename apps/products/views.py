from django.db.models import Q
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from .models import Product, Order, OrderItem
from ..accounts.models import CustomUser
from django.contrib import messages
from apps.finance.services import create_sales_voucher


def clean_quantity_by_unit(product, raw_qty):
    """
    ইউনিট অনুযায়ী পরিমাণের মান ফিল্টার করার ফাংশন:
    - pcs, ati, fana -> সবসময় পূর্ণসংখ্যা (int) হবে (যেমন: 1, 2, 3)
    - kg, hali       -> ফ্র্যাকশন হতে পারবে (যেমন: 0.5, 1.5)
    - gm             -> গ্রামে ইনপুট (যেমন: 250, 500)
    """
    try:
        qty = float(raw_qty)
    except (ValueError, TypeError):
        qty = 1.0

    if qty <= 0:
        qty = 1.0

    # পিস, আঁটি বা ফানা হলে ফ্র্যাকশন এলাউ করা হবে না (পূর্ণসংখ্যায় রূপান্তর)
    if product.unit in ['pcs', 'ati', 'fana']:
        qty = float(int(qty))
        if qty < 1.0:
            qty = 1.0

    return qty


def shop(request):
    query = request.GET.get('q')
    products = Product.objects.filter(is_active=True)

    if query:
        products = products.filter(
            Q(name__icontains=query) |
            Q(description__icontains=query)
        )

    return render(request, 'products/shop.html', {
        'products': products,
        'query': query
    })


@login_required
def add_to_cart(request, product_id):
    product = get_object_or_404(Product, id=product_id, is_active=True)
    cart = request.session.get('cart', {})

    raw_qty = request.POST.get('quantity', 1)
    qty = clean_quantity_by_unit(product, raw_qty)

    pid = str(product_id)
    if pid in cart:
        cart[pid] += qty
    else:
        cart[pid] = qty

    request.session['cart'] = cart
    messages.success(request, f"{product.name} added to cart!")

    return redirect('cart')

@login_required
def cart(request):
    cart = request.session.get('cart', {})

    if request.method == 'POST':

        remove_product_id = request.POST.get('remove_product')
        if remove_product_id:
            cart.pop(str(remove_product_id), None)
            if remove_product_id.isdigit():
                cart.pop(int(remove_product_id), None)
            request.session['cart'] = cart
            return redirect('cart')

        # ২. সাধারণ Quantity Update
        for key, value in request.POST.items():
            if key.startswith('qty_'):
                product_id = key.replace('qty_', '')
                product = Product.objects.filter(id=product_id).first()

                if product:
                    qty = clean_quantity_by_unit(product, value)
                    if qty <= 0:
                        cart.pop(str(product_id), None)
                        cart.pop(int(product_id), None)
                    else:
                        cart[str(product_id)] = qty

        request.session['cart'] = cart
        return redirect('cart')

    items = []
    total = 0

    for pid, qty in list(cart.items()):
        product = Product.objects.filter(id=pid, is_active=True).first()
        if product:
            # মডেলে আপডেট করা calculate_price() মেথড দিয়ে গ্রামের সঠিক হিসাব
            item_total = product.calculate_price(qty)

            items.append({
                'product': product,
                'quantity': qty,
                'total': item_total
            })

            total += item_total
        else:
            # Inactive or deleted product removed from active cart
            cart.pop(str(pid), None)
            request.session['cart'] = cart

    return render(request, 'products/cart.html', {
        'items': items,
        'total': total
    })


@login_required
def order_confirm(request):
    cart = request.session.get('cart', {})
    items = []
    total = 0

    for pid, qty in list(cart.items()):
        product = Product.objects.filter(id=pid, is_active=True).first()
        if product:
            item_total = product.calculate_price(qty)

            items.append({
                'product': product,
                'quantity': qty,
                'remarks': '-',
                'total': item_total
            })

            total += item_total
        else:
            cart.pop(str(pid), None)
            request.session['cart'] = cart

    return render(request, 'products/order_confirm.html', {
        'items': items,
        'total': total
    })


@login_required
def confirm_order(request):
    if request.method == "POST":
        cart = request.session.get("cart", {})

        if not cart:
            return redirect("cart")

        order = Order.objects.create(
            user=request.user
        )

        for pid, qty in list(cart.items()):
            product = Product.objects.filter(id=pid, is_active=True).first()
            if product:
                OrderItem.objects.create(
                    order=order,
                    product=product,
                    quantity=float(qty),
                    price_at_order_time=product.price
                )

        request.session["cart"] = {}

        return redirect("profile")

    return redirect("cart")


@login_required
def send_to_supplier(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    supplier = CustomUser.objects.filter(is_staff=True).first()

    order.assigned_to = supplier
    order.status = 'sent_to_uthaan_krishi'
    order.save()

    return redirect('admin:index')


def product_details(request, id):
    product = get_object_or_404(
        Product,
        id=id,
        is_active=True
    )

    context = {
        "product": product
    }

    return render(
        request,
        "products/product_details.html",
        context
    )

