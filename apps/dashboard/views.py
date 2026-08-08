from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.core.exceptions import PermissionDenied
from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import render
from django.db.models import Q
from apps.accounts.models import CustomUser
from apps.finance.models import Journal
from apps.finance.services import create_journal, receive_payment_service
from apps.finance.views import receive_payment
from apps.products.models import Product, Order, OrderItem
from apps.finance.models import Journal, Account
from django.shortcuts import render, redirect
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
# SUPPLIER PANEL (UPDATED)
# =========================
@login_required
def supplier_panel(request):
    if request.method == "POST":
        print("POST RECEIVED")
        print(request.POST)

    if not request.user.is_staff:
        raise PermissionDenied()

    search_query = request.GET.get("q", "")

    orders = Order.objects.filter(
        assigned_to=request.user
    ).exclude(
        status__in=["pending", "rejected"]
    )

    # SEARCH
    if search_query:
        orders = orders.filter(
            Q(id__icontains=search_query) |
            Q(order_code__icontains=search_query) |
            Q(user__username__icontains=search_query) |
            Q(user__id__icontains=search_query)
        )

    orders = orders.prefetch_related(
        "items",
        "items__product"
    ).order_by("-created_at")

    if request.method == "POST":

        order_id = request.POST.get("order_id")

        if order_id:

            order = get_object_or_404(
                Order,
                id=order_id,
                assigned_to=request.user
            )

            # =============================
            # SAVE ALL CHANGES
            # =============================
            for item in order.items.all():

                qty = request.POST.get(f"qty_{item.id}")
                remark = request.POST.get(f"remark_{item.id}")
                status = request.POST.get(f"status_{item.id}")

                # Updated Quantity
                if qty not in [None, ""]:
                    try:
                        item.updated_quantity = float(qty)
                    except ValueError:
                        pass

                # Remark
                if remark is not None:
                    item.remarks = remark

                # Status
                if status in ["pending", "accepted", "rejected"]:
                    item.status = status

                item.save()

            # =============================
            # UPDATE ORDER STATUS
            # =============================
            total_items = order.items.count()

            reviewed_items = order.items.filter(
                status__in=["accepted", "rejected"]
            ).count()

            if total_items > 0 and total_items == reviewed_items:
                order.status = "supplier_done"
            else:
                order.status = "sent_to_uthaan_krishi"

            order.save()

            messages.success(request, "Changes saved successfully.")

            return redirect("supplier_panel")

    return render(
        request,
        "dashboard/supplier.html",
        {
            "orders": orders,
            "search_query": search_query,
        },
    )
# =========================
# ORDERS VIEW (FIXED)
# =========================
@login_required
def orders_view(request):

    user = request.user

    search_query = request.GET.get('q', '')

    if not user.is_staff:

        orders = Order.objects.filter(
            user=user
        )

        if search_query:
            orders = orders.filter(
                Q(user__username__icontains=search_query) |
                Q(user__id__icontains=search_query) |
                Q(order_code__icontains=search_query)
            )

        orders = orders.prefetch_related(
            'items', 'items__product'
        ).order_by('-created_at')

        return render(request, 'dashboard/user_orders.html', {
            'orders': orders,
            'search_query': search_query
        })

    orders = Order.objects.filter(
        assigned_to=user
    ).exclude(
        status__in=['pending', 'rejected']
    )

    if search_query:
        orders = orders.filter(
            Q(user__username__icontains=search_query) |
            Q(user__id__icontains=search_query) |
            Q(order_code__icontains=search_query)
        )

    # Staff/Supplier হলে supplier_panel view-তে পাঠাও
    return redirect("supplier_panel")


# =========================
# ADMIN PANEL (CLEANED)
# =========================
@login_required
@user_passes_test(is_admin)
def admin_panel(request):

    active_tab = request.GET.get('tab') or request.POST.get('tab') or 'users'

    user_query = request.GET.get('uq', '')
    product_query = request.GET.get('pq', '')
    order_query = request.GET.get('oq', '')

    # USERS
    users = CustomUser.objects.all()
    if user_query:
        users = users.filter(
            Q(username__icontains=user_query) |
            Q(email__icontains=user_query) |
            Q(phone_number__icontains=user_query)
        )

    # PRODUCTS
    products = Product.objects.all()
    if product_query:
        products = products.filter(
            Q(name__icontains=product_query) |
            Q(description__icontains=product_query)
        )

    # ORDERS
    orders = Order.objects.all().prefetch_related(
        'items',
        'items__product'
    ).order_by('-id')

    if order_query:
        orders = orders.filter(
            order_code__icontains=order_query
        )

    for order in orders:
        customer_account = Account.objects.filter(
            customer=order.user,
            type1="customer"
        ).first()

        order.customer_account_id = (
            customer_account.id if customer_account else None
        )

        # ADD THIS
        order.journal = order.journals.order_by("-id").first()
    # =====================
    # POST UPDATE LOGIC
    # =====================
    if request.method == "POST":

        order_id = request.POST.get("order_id")

        if order_id:
            order = get_object_or_404(Order, id=order_id)

            # ITEMS UPDATE
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

            # ASSIGN USER (FIXED SAFE)
            assigned_user_id = request.POST.get("assigned_user")

            if assigned_user_id:
                order.assigned_to_id = assigned_user_id
                order.status = "sent_to_uthaan_krishi"

            # STATUS UPDATE
            status = request.POST.get("status")

            if status:
                valid_statuses = [x[0] for x in Order.STATUS_CHOICES]

                if status in valid_statuses:
                    order.status = status

                    if status == "accepted":
                        order.items.filter(is_admin_added=True).update(
                            is_visible_to_user=True
                        )

            # ADD PRODUCT
            new_product_id = request.POST.get("new_product_id")
            new_qty = request.POST.get("new_qty")

            if new_product_id and new_qty:

                product = Product.objects.filter(
                    id=new_product_id
                ).first()

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
            # ==========================================
            # BKASH CHARGE TOGGLE
            # ==========================================

            order.apply_bkash_charge = (
                    request.POST.get("apply_bkash_charge") == "on"
            )
            # ==========================================
            # DISCOUNT / PACKAGING
            # ==========================================

            for field, attr in [

                ("discount", "discount"),
                ("packaging_charge", "packaging_charge"),

            ]:

                value = request.POST.get(field)

                if value not in [None, ""]:

                    try:

                        setattr(
                            order,
                            attr,
                            float(value)
                        )

                    except ValueError:

                        pass

            order.save()

            # ==========================================
            # CREATE / UPDATE JOURNAL
            # ==========================================

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
# USER DELETE
# =========================
@login_required
@user_passes_test(is_admin)
def delete_user(request, user_id):

    user = get_object_or_404(CustomUser, id=user_id)

    if user != request.user:
        user.delete()

    return redirect('admin_panel')





# =========================
# ORDER ACTIONS
# =========================
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

    # Create Cash Ledger Entry
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

    return render(request, 'dashboard/edit_user.html', {
        'user': user
    })
@login_required
@user_passes_test(is_admin)
def user_detail(request, user_id):

    user = get_object_or_404(CustomUser, id=user_id)

    return render(request, 'dashboard/user_detail.html', {
        'user_obj': user
    })

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

    return render(request, 'dashboard/product_detail.html', {
        'product': product
    })
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

    return render(request, 'dashboard/edit_profile.html', {
        'user': user
    })
@login_required
@user_passes_test(is_admin)
def admin_order_detail(request, pk):

    # ==========================================
    # GET ORDER
    # ==========================================
    order = get_object_or_404(
        Order.objects.prefetch_related(
            "items",
            "items__product",
        ),
        pk=pk,
    )

    users = CustomUser.objects.filter(is_staff=True)
    products = Product.objects.all()

    # ==========================================
    # CUSTOMER ACCOUNT
    # ==========================================

    customer_account = Account.objects.filter(
        customer=order.user,
        type1="asset",
        type2="customer",
    ).first()

    order.customer_account_id = (
        customer_account.id if customer_account else None
    )

    order.customer_account_id = (
        customer_account.id if customer_account else None
    )

    # ==========================================
    # LATEST JOURNAL
    # ==========================================
    order.journal = order.journals.order_by("-id").first()

    # ==========================================
    # POST REQUEST
    # ==========================================
    if request.method == "POST":

        # ======================================
        # UPDATE ORDER ITEMS
        # ======================================
        for item in order.items.all():

            qty = request.POST.get(f"qty_{item.id}")
            remark = request.POST.get(f"remark_{item.id}")
            item_status = request.POST.get(f"status_{item.id}")

            # Quantity
            if qty not in [None, ""]:
                try:
                    item.updated_quantity = float(qty)
                except ValueError:
                    pass

            # Remarks
            if remark is not None:
                item.remarks = remark

            # Item Status
            if item_status in [
                "pending",
                "accepted",
                "rejected",
                "complimentary",
            ]:
                item.status = item_status

            # Complimentary Item
            if item_status == "complimentary":
                item.price_at_order_time = 0
                item.updated_quantity = (
                    item.updated_quantity or item.quantity
                )

            # Rejected Item
            if item_status == "rejected":
                item.updated_quantity = 0

            item.save()

        # ======================================
        # PART 2 STARTS FROM HERE
        # ======================================

        # ======================================
        # ASSIGN STAFF
        # ======================================
        assigned_user_id = request.POST.get("assigned_user")

        if assigned_user_id:
            order.assigned_to_id = assigned_user_id
            order.status = "sent_to_uthaan_krishi"

        # ======================================
        # ORDER STATUS
        # ======================================
        status = request.POST.get("status")

        if status:

            valid_statuses = [
                choice[0] for choice in Order.STATUS_CHOICES
            ]

            if status in valid_statuses:

                order.status = status

                if status == "accepted":
                    order.items.filter(
                        is_admin_added=True
                    ).update(
                        is_visible_to_user=True
                    )

        # ======================================
        # ADD NEW PRODUCT
        # ======================================
        new_product_id = request.POST.get("new_product_id")
        new_qty = request.POST.get("new_qty")

        if new_product_id and new_qty:

            product = Product.objects.filter(
                id=new_product_id
            ).first()

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

        # ======================================
        # BKASH CHARGE
        # ======================================
        order.apply_bkash_charge = (
            request.POST.get("apply_bkash_charge") == "on"
        )

        # ======================================
        # DISCOUNT & PACKAGING
        # ======================================
        for field, attr in [
            ("discount", "discount"),
            ("packaging_charge", "packaging_charge"),
        ]:

            value = request.POST.get(field)

            if value not in [None, ""]:

                try:

                    setattr(
                        order,
                        attr,
                        float(value)
                    )

                except ValueError:
                    pass

        # ======================================
        # PART 3 STARTS FROM HERE
        # ======================================

        # ======================================
        # SAVE ORDER
        # ======================================
        order.save()

        # ======================================
        # CREATE / UPDATE JOURNAL
        # ======================================
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

        # ======================================
        # RELOAD LATEST JOURNAL
        # ======================================
        order.journal = order.journals.order_by("-id").first()

        # ======================================
        # REDIRECT AFTER SAVE
        # ======================================
        return redirect(
            "admin_order_detail",
            pk=order.pk
        )

    # ==========================================
    # PAGE RENDER
    # ==========================================
    return render(
        request,
        "dashboard/order_detail.html",
        {
            "order": order,
            "users": users,
            "products": products,
        },
    )