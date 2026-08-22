from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.core.exceptions import PermissionDenied
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Q
from apps.accounts.models import CustomUser
from apps.products.models import Product, Order, OrderItem
from apps.finance.models import Journal, Account
from apps.finance.services import create_journal, receive_payment_service
from apps.finance.views import receive_payment

UNIT_CHOICES = Product.UNIT_CHOICES


# =========================
# ADMIN CHECK
# =========================
def is_admin(user):
    return user.is_authenticated and user.is_superuser


# =========================
# PROFILE
# =========================
@login_required
def profile_view(request):
    return render(request, 'dashboard/profile.html', {
        'user': request.user
    })


# =========================
# USER ORDERS LIST & DETAIL
# =========================
@login_required
def user_order_list(request):
    """ কাস্টমারের সব অর্ডারের তালিকা ও সার্চ """
    search_query = request.GET.get('q', '').strip()

    orders = Order.objects.filter(user=request.user).prefetch_related('items', 'items__product').order_by('-created_at')

    if search_query:
        user_filter = Q(order_code__icontains=search_query) | Q(items__product__name__icontains=search_query)
        if search_query.isdigit():
            user_filter |= Q(id=int(search_query))
        orders = orders.filter(user_filter).distinct()

    return render(request, 'dashboard/user_order_list.html', {
        'orders': orders,
        'search_query': search_query,
    })


@login_required
def user_order_detail(request, order_id):
    """ একটি নির্দিষ্ট অর্ডারের বিস্তারিত মেমো/বিল দেখার ভিউ """
    order = get_object_or_404(
        Order.objects.prefetch_related('items', 'items__product'),
        id=order_id,
        user=request.user
    )

    return render(request, 'dashboard/user_order_detail.html', {
        'order': order
    })


# =========================
# STAFF / SUPPLIER LIST & DETAIL
# =========================
@login_required
def staff_order_list(request):
    """ স্টাফের কাছে Assign করা সব অর্ডারের তালিকা """
    if not request.user.is_staff:
        raise PermissionDenied()

    search_query = request.GET.get('q', '').strip()

    orders = Order.objects.filter(
        assigned_to=request.user
    ).exclude(
        status__in=['pending', 'rejected']
    ).prefetch_related('items', 'items__product').order_by('-created_at')

    if search_query:
        user_filter = Q(order_code__icontains=search_query) | Q(user__username__icontains=search_query)
        if search_query.isdigit():
            user_filter |= Q(id=int(search_query)) | Q(user__user_id=int(search_query))
        orders = orders.filter(user_filter).distinct()

    return render(request, 'dashboard/staff_order_list.html', {
        'orders': orders,
        'search_query': search_query,
    })


@login_required
def staff_order_detail(request, order_id):
    """ একটি নির্দিষ্ট অর্ডার রিভিউ এবং এডিট করার জন্য স্টাফ প্যানেল """
    if not request.user.is_staff:
        raise PermissionDenied()

    order = get_object_or_404(
        Order.objects.prefetch_related('items', 'items__product'),
        id=order_id,
        assigned_to=request.user
    )

    if request.method == "POST":
        for item in order.items.all():
            qty = request.POST.get(f"qty_{item.id}")
            remark = request.POST.get(f"remark_{item.id}")
            status = request.POST.get(f"status_{item.id}")

            if qty not in [None, ""]:
                try:
                    item.updated_quantity = float(qty)
                except ValueError:
                    pass

            if remark is not None:
                item.remarks = remark

            if status in ["pending", "accepted", "rejected"]:
                item.status = status

            item.save()

        total_items = order.items.count()
        reviewed_items = order.items.filter(status__in=["accepted", "rejected"]).count()

        if total_items > 0 and total_items == reviewed_items:
            order.status = "supplier_done"
        else:
            order.status = "sent_to_uthaan_krishi"

        order.save()
        messages.success(request, "Changes saved successfully.")
        return redirect("staff_order_detail", order_id=order.id)

    return render(request, "dashboard/supplier.html", {
        "order": order,
    })


@login_required
def supplier_panel(request):
    return redirect("staff_orders")


@login_required
def orders_view(request):
    if request.user.is_staff:
        return redirect("staff_orders")
    return redirect("user_orders")


# =========================
# ADMIN PANEL
# =========================
@login_required
@user_passes_test(is_admin)
def admin_panel(request):
    active_tab = request.GET.get('tab') or request.POST.get('tab') or 'users'

    user_query = request.GET.get('uq', '')
    product_query = request.GET.get('pq', '')
    order_query = request.GET.get('oq', '')

    users = CustomUser.objects.all()
    if user_query:
        user_filters = (
                Q(username__icontains=user_query) |
                Q(email__icontains=user_query) |
                Q(phone_number__icontains=user_query)
        )
        if user_query.isdigit():
            user_filters |= Q(user_id=int(user_query))
        users = users.filter(user_filters)

    products = Product.objects.all()
    if product_query:
        products = products.filter(
            Q(name__icontains=product_query) |
            Q(description__icontains=product_query)
        )

    orders = Order.objects.all().prefetch_related(
        'items',
        'items__product'
    ).order_by('-id')

    if order_query:
        order_filters = Q(order_code__icontains=order_query)
        if order_query.isdigit():
            order_filters |= Q(user__user_id=int(order_query))
        orders = orders.filter(order_filters)

    for order in orders:
        customer_account = Account.objects.filter(
            customer=order.user,
            type1="customer"
        ).first()

        order.customer_account_id = (
            customer_account.id if customer_account else None
        )
        order.journal = order.journals.order_by("-id").first()

    if request.method == "POST":
        order_id = request.POST.get("order_id")

        if order_id:
            order = get_object_or_404(Order, id=order_id)

            for item in order.items.all():
                qty = request.POST.get(f'qty_{item.id}')
                remark = request.POST.get(f'remark_{item.id}')
                item_status = request.POST.get(f'status_{item.id}')

                if qty not in [None, ""]:
                    try:
                        item.updated_quantity = float(qty)
                    except ValueError:
                        pass

                if remark is not None:
                    item.remarks = remark

                if item_status in ['pending', 'accepted', 'rejected', 'complimentary']:
                    item.status = item_status

                if item_status == "complimentary":
                    item.price_at_order_time = 0
                    item.updated_quantity = item.updated_quantity or item.quantity

                if item_status == "rejected":
                    item.updated_quantity = 0

                item.save()

            assigned_user_id = request.POST.get("assigned_user")
            if assigned_user_id:
                order.assigned_to_id = assigned_user_id
                order.status = "sent_to_uthaan_krishi"

            status = request.POST.get("status")
            if status:
                valid_statuses = [x[0] for x in Order.STATUS_CHOICES]
                if status in valid_statuses:
                    order.status = status
                    if status == "accepted":
                        order.items.filter(is_admin_added=True).update(
                            is_visible_to_user=True
                        )

            new_product_id = request.POST.get("new_product_id")
            new_qty = request.POST.get("new_qty")

            if new_product_id and new_qty:
                product = Product.objects.filter(id=new_product_id).first()
                if product:
                    try:
                        qty = float(new_qty)
                        if product.unit not in ["kg", "gm"]:
                            qty = int(qty)
                        OrderItem.objects.create(
                            order=order,
                            product=product,
                            quantity=qty,
                            price_at_order_time=product.price,
                            is_admin_added=True,
                            is_visible_to_user=False,
                        )
                    except ValueError:
                        pass

            order.apply_bkash_charge = (
                    request.POST.get("apply_bkash_charge") == "on"
            )

            for field, attr in [
                ("discount", "discount"),
                ("packaging_charge", "packaging_charge"),
            ]:
                value = request.POST.get(field)
                if value not in [None, ""]:
                    try:
                        setattr(order, attr, float(value))
                    except ValueError:
                        pass

            order.save()

            if order.status == "accepted":
                journal = order.journals.order_by("-id").first()
                if journal is None:
                    journal = create_journal(order)
                journal.subtotal = order.updated_total_price
                journal.discount = order.discount
                journal.packaging_charge = order.packaging_charge
                journal.bkash_charge = order.bkash_charge
                journal.grand_total = order.final_payment
                journal.save()

            return redirect(request.path)

    return render(
        request,
        "dashboard/admin_panel.html",
        {
            "users": users,
            "products": products,
            "orders": orders,
            "user_query": user_query,
            "product_query": product_query,
            "order_query": order_query,
            "active_tab": active_tab,
        },
    )


# =========================
# OTHER ADMIN / PROFILE ACTIONS
# =========================
@login_required
@user_passes_test(is_admin)
def delete_user(request, user_id):
    user = get_object_or_404(CustomUser, id=user_id)
    if user != request.user:
        user.delete()
    return redirect('admin_panel')


@login_required
@user_passes_test(is_admin)
def send_to_supplier_admin(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    supplier = CustomUser.objects.filter(is_staff=True).first()
    order.assigned_to = supplier
    order.status = 'sent_to_uthaan_krishi'
    order.save()
    return redirect('admin_panel')


@login_required
@user_passes_test(is_admin)
def accept_order(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    order.status = 'accepted'
    order.save()
    return redirect('admin_panel')


@login_required
@user_passes_test(is_admin)
def reject_order(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    order.status = 'rejected'
    order.save()
    return redirect('admin_panel')


@login_required
@user_passes_test(is_admin)
def payment_done(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    order.status = "payment_done"
    order.save()
    receive_payment(order)
    return redirect("admin_panel")


@login_required
@user_passes_test(is_admin)
def delivery_done(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    order.status = 'delivery_done'
    order.save()
    return redirect('admin_panel')


@login_required
@user_passes_test(is_admin)
def edit_user(request, user_id):
    user = get_object_or_404(CustomUser, id=user_id)
    if request.method == "POST":
        user.username = request.POST.get("username")
        user.email = request.POST.get("email")
        user.phone_number = request.POST.get("phone_number")
        user.location = request.POST.get("location")
        user.country = request.POST.get("country")

        role = request.POST.get("role")
        if role == "admin":
            user.is_staff = True
            user.is_superuser = True
        elif role == "staff":
            user.is_staff = True
            user.is_superuser = False
        else:
            user.is_staff = False
            user.is_superuser = False

        user.save()
        return redirect('user_detail', user_id=user.id)

    return render(request, 'dashboard/edit_user.html', {'user': user})


@login_required
@user_passes_test(is_admin)
def user_detail(request, user_id):
    user = get_object_or_404(CustomUser, id=user_id)
    return render(request, 'dashboard/user_detail.html', {'user_obj': user})


@login_required
@user_passes_test(is_admin)
def add_product(request):
    if request.method == "POST":
        Product.objects.create(
            name=request.POST.get("name"),
            price=request.POST.get("price"),
            unit=request.POST.get("unit"),
            description=request.POST.get("description"),
            image=request.FILES.get("image")
        )
        return redirect('admin_panel')

    return render(request, 'dashboard/add_product.html', {
        'unit_choices': Product.UNIT_CHOICES
    })


@login_required
@user_passes_test(is_admin)
def edit_product(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    if request.method == "POST":
        product.name = request.POST.get("name", product.name)
        price = request.POST.get("price")
        if price:
            try:
                product.price = float(price)
            except ValueError:
                pass
        product.unit = request.POST.get("unit", product.unit)
        product.description = request.POST.get("description", product.description)

        if request.FILES.get("image"):
            product.image = request.FILES.get("image")

        product.save()
        return redirect('product_detail', product_id=product.id)

    return render(request, 'dashboard/edit_product.html', {
        'product': product,
        'unit_choices': Product.UNIT_CHOICES
    })


@login_required
@user_passes_test(is_admin)
def product_detail(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    return render(request, 'dashboard/product_detail.html', {'product': product})


@login_required
@user_passes_test(is_admin)
def delete_product(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    if product.image:
        product.image.delete()
    product.delete()
    return redirect('admin_panel')


@login_required
@user_passes_test(is_admin)
def update_order_status(request, order_id, status):
    order = get_object_or_404(Order, id=order_id)
    valid_statuses = dict(Order.STATUS_CHOICES).keys()
    if status in valid_statuses:
        order.status = status
        order.save()
    return redirect('admin_panel')


@login_required
@user_passes_test(is_admin)
def assign_order_user(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    if request.method == "POST":
        user_id = request.POST.get("assigned_user")
        if user_id:
            user = get_object_or_404(CustomUser, id=user_id)
            order.assigned_to = user
            order.status = "sent_to_uthaan_krishi"
            order.save()
    return redirect('admin_panel')


@login_required
def edit_profile(request):
    user = request.user
    if request.method == "POST":
        user.username = request.POST.get("username")
        user.email = request.POST.get("email")
        user.phone_number = request.POST.get("phone_number")
        user.location = request.POST.get("location")
        user.country = request.POST.get("country")

        if request.FILES.get("profile_image"):
            user.profile_image = request.FILES.get("profile_image")

        user.save()
        return redirect('profile')

    return render(request, 'dashboard/edit_profile.html', {'user': user})


@login_required
@user_passes_test(is_admin)
def admin_order_detail(request, pk):
    order = get_object_or_404(
        Order.objects.prefetch_related("items", "items__product"),
        pk=pk,
    )
    users = CustomUser.objects.filter(is_staff=True)
    products = Product.objects.all()

    customer_account = Account.objects.filter(
        customer=order.user,
        type1="asset",
        type2="customer",
    ).first()
    order.customer_account_id = (customer_account.id if customer_account else None)
    order.journal = order.journals.order_by("-id").first()

    if request.method == "POST":
        for item in order.items.all():
            qty = request.POST.get(f"qty_{item.id}")
            remark = request.POST.get(f"remark_{item.id}")
            item_status = request.POST.get(f"status_{item.id}")

            if qty not in [None, ""]:
                try:
                    item.updated_quantity = float(qty)
                except ValueError:
                    pass

            if remark is not None:
                item.remarks = remark

            if item_status in ["pending", "accepted", "rejected", "complimentary"]:
                item.status = item_status

            if item_status == "complimentary":
                item.price_at_order_time = 0
                item.updated_quantity = item.updated_quantity or item.quantity

            if item_status == "rejected":
                item.updated_quantity = 0

            item.save()

        assigned_user_id = request.POST.get("assigned_user")
        if assigned_user_id:
            order.assigned_to_id = assigned_user_id
            order.status = "sent_to_uthaan_krishi"

        status = request.POST.get("status")
        if status:
            valid_statuses = [choice[0] for choice in Order.STATUS_CHOICES]
            if status in valid_statuses:
                order.status = status
                if status == "accepted":
                    order.items.filter(is_admin_added=True).update(is_visible_to_user=True)

        new_product_id = request.POST.get("new_product_id")
        new_qty = request.POST.get("new_qty")

        if new_product_id and new_qty:
            product = Product.objects.filter(id=new_product_id).first()
            if product:
                try:
                    qty = float(new_qty)
                    if product.unit not in ["kg", "gm"]:
                        qty = int(qty)
                    OrderItem.objects.create(
                        order=order,
                        product=product,
                        quantity=qty,
                        price_at_order_time=product.price,
                        is_admin_added=True,
                        is_visible_to_user=False,
                    )
                except ValueError:
                    pass

        order.apply_bkash_charge = (request.POST.get("apply_bkash_charge") == "on")

        for field, attr in [("discount", "discount"), ("packaging_charge", "packaging_charge")]:
            value = request.POST.get(field)
            if value not in [None, ""]:
                try:
                    setattr(order, attr, float(value))
                except ValueError:
                    pass

        order.save()

        if order.status == "accepted":
            journal = order.journals.order_by("-id").first()
            if journal is None:
                journal = create_journal(order)
            journal.subtotal = order.updated_total_price
            journal.discount = order.discount
            journal.packaging_charge = order.packaging_charge
            journal.bkash_charge = order.bkash_charge
            journal.grand_total = order.final_payment
            journal.save()

        order.journal = order.journals.order_by("-id").first()
        return redirect("admin_order_detail", pk=order.pk)

    return render(request, "dashboard/order_detail.html", {
        "order": order,
        "users": users,
        "products": products,
    })