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


@login_required
def order_receipt_pdf(request, order_id):
    """
    Generates a professional Order Receipt PDF.
    Accessible by the order owner (customer) and staff/superuser.
    """
    if request.user.is_staff or request.user.is_superuser:
        order = get_object_or_404(Order.objects.prefetch_related('items', 'items__product'), id=order_id)
    else:
        order = get_object_or_404(Order.objects.prefetch_related('items', 'items__product'), id=order_id, user=request.user)

    from django.http import HttpResponse

    import sys, types
    if 'PIL' not in sys.modules or sys.modules['PIL'] is None or not hasattr(sys.modules['PIL'], 'Image'):
        m = types.ModuleType('PIL')
        m.Image = types.ModuleType('Image')
        sys.modules['PIL'] = m
        sys.modules['PIL.Image'] = m
        sys.modules['_imaging'] = None
        sys.modules['PIL._imaging'] = None

    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4

    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="Order_Receipt_#{order.order_code}.pdf"'

    pdf = canvas.Canvas(response, pagesize=A4)
    width, height = A4

    # Top Yellow Header Banner
    y = height - 40
    pdf.setFillColorRGB(1.0, 0.90, 0.50)  # #ffe680
    pdf.rect(30, y - 10, width - 60, 30, fill=1, stroke=1)

    pdf.setFont("Helvetica-Bold", 14)
    pdf.setFillColorRGB(0.1, 0.1, 0.1)
    pdf.drawCentredString(width / 2.0, y, f"Amader Uthaan Krishi Bill — Order #{order.order_code}")

    # Meta Customer & Order Info
    y -= 35
    pdf.setFont("Helvetica-Bold", 9)
    pdf.setFillColorRGB(0.2, 0.2, 0.2)
    pdf.drawString(35, y, f"Date: {order.created_at.strftime('%d.%m.%Y')}")
    pdf.drawString(200, y, f"Customer: {order.user.username}")
    pdf.drawRightString(width - 35, y, f"Status: {order.get_status_display()}")

    # Table Header (Blue #0070c0)
    y -= 25
    pdf.setFillColorRGB(0.0, 0.44, 0.75)  # #0070c0
    pdf.rect(35, y - 5, width - 70, 20, fill=1, stroke=0)

    pdf.setFont("Helvetica-Bold", 9)
    pdf.setFillColorRGB(1.0, 1.0, 1.0)
    pdf.drawString(40, y, "SL")
    pdf.drawString(75, y, "Product Name")
    pdf.drawString(290, y, "Qty")
    pdf.drawRightString(430, y, "Unit Price")
    pdf.drawRightString(550, y, "Total")

    y_curr = y - 20
    pdf.setFont("Helvetica", 9)

    counter = 1
    items = order.items.all()
    for item in items:
        if item.is_admin_added and not item.is_visible_to_user and not (request.user.is_staff or request.user.is_superuser):
            continue

        prod_name = str(item.product.name)
        if item.status == 'complimentary':
            prod_name += " (Complimentary)"

        qty_str = item.formatted_qty_unit
        price_val = item.price_at_order_time if item.price_at_order_time is not None else item.product.price
        total_val = item.updated_total if order.status == "accepted" else item.total_price()

        pdf.setFillColorRGB(0.15, 0.15, 0.15)
        pdf.drawString(40, y_curr, str(counter))
        pdf.drawString(75, y_curr, prod_name[:36])
        pdf.drawString(290, y_curr, str(qty_str))
        pdf.drawRightString(430, y_curr, f"{price_val:.2f} BDT")
        pdf.drawRightString(550, y_curr, f"{total_val:.2f} BDT")

        # Row line
        pdf.setStrokeColorRGB(0.85, 0.85, 0.85)
        pdf.setLineWidth(0.5)
        pdf.line(35, y_curr - 4, width - 35, y_curr - 4)

        y_curr -= 18
        counter += 1

        if y_curr < 140:
            pdf.showPage()
            y_curr = height - 50

    # Summary & Payment Details
    y_curr -= 10
    pdf.setStrokeColorRGB(0.8, 0.8, 0.8)
    pdf.setLineWidth(1)
    pdf.line(35, y_curr + 5, width - 35, y_curr + 5)

    # bKash Card Box on Left
    if order.status == "accepted":
        pdf.setFillColorRGB(1.0, 0.96, 0.96)  # #fff5f5
        pdf.setStrokeColorRGB(0.90, 0.22, 0.21)  # red dashed border
        pdf.rect(35, y_curr - 65, 230, 60, fill=1, stroke=1)

        pdf.setFont("Helvetica-Bold", 9)
        pdf.setFillColorRGB(0.1, 0.1, 0.1)
        pdf.drawString(42, y_curr - 18, "Payment Instructions")
        pdf.setFont("Helvetica", 8)
        pdf.setFillColorRGB(0.4, 0.4, 0.4)
        pdf.drawString(42, y_curr - 32, "Please send bill amount via bKash:")
        pdf.setFont("Helvetica-Bold", 10)
        pdf.setFillColorRGB(0.75, 0.0, 0.0)  # #c00000
        pdf.drawString(42, y_curr - 48, "bKash Number: 01403181484")

        # Summary Values on Right
        pdf.setFont("Helvetica", 9)
        pdf.setFillColorRGB(0.3, 0.3, 0.3)

        pdf.drawString(300, y_curr - 12, "Discount:")
        pdf.drawRightString(550, y_curr - 12, f"- {order.discount or 0:.2f} BDT")

        pdf.drawString(300, y_curr - 26, "Packaging & Delivery:")
        pdf.drawRightString(550, y_curr - 26, f"{order.packaging_charge or 0:.2f} BDT")

        pdf.setFont("Helvetica-Bold", 9.5)
        pdf.setFillColorRGB(0.0, 0.44, 0.75)
        pdf.drawString(300, y_curr - 40, "Final Total:")
        pdf.drawRightString(550, y_curr - 40, f"{order.final_total:.2f} BDT")

        pdf.setFillColorRGB(0.1, 0.53, 0.33)
        pdf.drawString(300, y_curr - 55, "Total Bill (with bKash):")
        pdf.drawRightString(550, y_curr - 55, f"{order.final_payment:.2f} BDT")

        y_curr -= 80
    else:
        pdf.setFont("Helvetica-Bold", 10)
        pdf.setFillColorRGB(0.0, 0.44, 0.75)
        pdf.drawString(300, y_curr - 15, "Total Price:")
        pdf.drawRightString(550, y_curr - 15, f"{order.total_price:.2f} BDT")
        y_curr -= 35

    # Footer Msg
    pdf.setFont("Helvetica-Oblique", 9)
    pdf.setFillColorRGB(0.44, 0.19, 0.63)  # #7030a0
    pdf.drawCentredString(width / 2.0, y_curr, "We hope you enjoy our fresh harvests — thank you for supporting Amader Uthaan Krishi!")

    pdf.save()
    return response


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
    return redirect('/dashboard/admin_panel/?tab=users')


@login_required
@user_passes_test(is_admin)
def send_to_supplier_admin(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    supplier = CustomUser.objects.filter(is_staff=True).first()
    order.assigned_to = supplier
    order.status = 'sent_to_uthaan_krishi'
    order.save()
    return redirect('/dashboard/admin_panel/?tab=orders')


@login_required
@user_passes_test(is_admin)
def accept_order(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    order.status = 'accepted'
    order.save()
    return redirect('/dashboard/admin_panel/?tab=orders')


@login_required
@user_passes_test(is_admin)
def reject_order(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    order.status = 'rejected'
    order.save()
    return redirect('/dashboard/admin_panel/?tab=orders')


@login_required
@user_passes_test(is_admin)
def payment_done(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    order.status = "payment_done"
    order.save()
    receive_payment(order)
    return redirect('/dashboard/admin_panel/?tab=orders')


@login_required
@user_passes_test(is_admin)
def delivery_done(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    order.status = 'delivery_done'
    order.save()
    return redirect('/dashboard/admin_panel/?tab=orders')


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
        is_active_val = request.POST.get("is_active", "on")
        is_active = (is_active_val in ["on", "1", "true", True])
        Product.objects.create(
            name=request.POST.get("name"),
            price=request.POST.get("price"),
            unit=request.POST.get("unit"),
            description=request.POST.get("description"),
            image=request.FILES.get("image"),
            is_active=is_active
        )
        return redirect('/dashboard/admin_panel/?tab=products')

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

        is_active_val = request.POST.get("is_active")
        product.is_active = (is_active_val in ["on", "1", "true", True])

        if request.FILES.get("image"):
            product.image = request.FILES.get("image")

        product.save()
        messages.success(request, f"Product '{product.name}' updated successfully.")
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
def toggle_product_status(request, product_id):
    """
    Toggles product between Active and Inactive without deleting data.
    """
    product = get_object_or_404(Product, id=product_id)
    product.is_active = not product.is_active
    product.save()
    status_txt = "Active (Visible in Shop)" if product.is_active else "Inactive (Hidden from Shop)"
    messages.success(request, f"Product '{product.name}' is now marked as {status_txt}.")
    return redirect('/dashboard/admin_panel/?tab=products')


@login_required
@user_passes_test(is_admin)
def delete_product(request, product_id):
    """
    Soft-delete: Deactivates product so it's hidden from shop, but retains
    all Chart of Accounts, Ledgers, Journals, and Order Items safely.
    """
    product = get_object_or_404(Product, id=product_id)
    product.is_active = False
    product.save()
    messages.success(request, f"Product '{product.name}' has been deactivated and hidden from shop. Chart of Accounts, Ledgers, and historical orders are 100% preserved.")
    return redirect('/dashboard/admin_panel/?tab=products')


@login_required
@user_passes_test(is_admin)
def update_order_status(request, order_id, status):
    order = get_object_or_404(Order, id=order_id)
    valid_statuses = dict(Order.STATUS_CHOICES).keys()
    if status in valid_statuses:
        order.status = status
        order.save()
    return redirect('/dashboard/admin_panel/?tab=orders')


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
    return redirect('/dashboard/admin_panel/?tab=orders')


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