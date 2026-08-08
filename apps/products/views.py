from django.db.models import Q
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from .models import Product, Order, OrderItem
from ..accounts.models import CustomUser
from django.contrib import messages
from apps.finance.services import create_sales_voucher
def shop(request):
    query = request.GET.get('q')
    products = Product.objects.all()

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

    product = get_object_or_404(Product, id=product_id)
    cart = request.session.get('cart', {})

    try:
        qty = int(request.POST.get('quantity', 1))
        if qty <= 0:
            qty = 1
    except:
        qty = 1

    if str(product_id) in cart:
        cart[str(product_id)] += qty
    else:
        cart[str(product_id)] = qty

    request.session['cart'] = cart
    messages.success(request, f"{product.name} added to cart!")

    return redirect('cart')

@login_required
def cart(request):
    cart = request.session.get('cart', {})

    if request.method == 'POST':
        for key, value in request.POST.items():

            if key.startswith('qty_'):
                product_id = key.replace('qty_', '')

                try:
                    qty = int(value)
                except:
                    qty = 1

                if qty <= 0:
                    cart.pop(product_id, None)
                else:
                    cart[product_id] = qty

        request.session['cart'] = cart
        return redirect('cart')

    items = []
    total = 0

    for pid, qty in cart.items():
        product = get_object_or_404(Product, id=pid)
        item_total = product.price * qty

        items.append({
            'product': product,
            'quantity': qty,
            'total': item_total
        })

        total += item_total

    return render(request, 'products/cart.html', {
        'items': items,
        'total': total
    })

@login_required
def order_confirm(request):
    cart = request.session.get('cart', {})
    items = []
    total = 0

    for pid, qty in cart.items():
        product = get_object_or_404(Product, id=pid)
        item_total = product.price * qty

        items.append({
            'product': product,
            'quantity': qty,
            'remarks': '-',
            'total': item_total
        })

        total += item_total

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

        for pid, qty in cart.items():

            product = get_object_or_404(Product, id=pid)

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
    order.status = 'Sent to Uthaan Krishi'
    order.save()

    return redirect('admin:index')


def product_details(request, id):

    product = get_object_or_404(
        Product,
        id=id
    )

    context = {
        "product": product
    }

    return render(
        request,
        "products/product_details.html",
        context
    )

