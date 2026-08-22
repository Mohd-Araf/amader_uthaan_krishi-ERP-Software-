from django.urls import path
from . import views

urlpatterns = [
    path('profile/', views.profile_view, name='profile'),
    path('profile/edit/', views.edit_profile, name='edit_profile'),

    # User Orders (List & Detail)
    path('my-orders/', views.user_order_list, name='user_orders'),
    path('my-orders/<int:order_id>/', views.user_order_detail, name='user_order_detail'),
    path('user_orders/', views.orders_view, name='user_orders_redirect'),

    # Staff / Supplier Orders (List & Detail)
    path('staff-orders/', views.staff_order_list, name='staff_orders'),
    path('staff-orders/<int:order_id>/', views.staff_order_detail, name='staff_order_detail'),
    path('supplier/', views.supplier_panel, name='supplier_panel'),

    # Admin Panel
    path('admin_panel/', views.admin_panel, name='admin_panel'),
    path("order/<int:pk>/", views.admin_order_detail, name="admin_order_detail"),
    path('user/delete/<int:user_id>/', views.delete_user, name='delete_user'),
    path('product/delete/<int:product_id>/', views.delete_product, name='delete_product'),
    path('order/send/<int:order_id>/', views.send_to_supplier_admin, name='send_to_supplier_admin'),
    path('order/accept/<int:order_id>/', views.accept_order, name='accept_order'),
    path('order/reject/<int:order_id>/', views.reject_order, name='reject_order'),
    path('order/payment/<int:order_id>/', views.payment_done, name='payment_done'),
    path('order/delivery/<int:order_id>/', views.delivery_done, name='delivery_done'),
    path('user/<int:user_id>/', views.user_detail, name='user_detail'),
    path('user/<int:user_id>/edit/', views.edit_user, name='edit_user'),
    path('product/add/', views.add_product, name='add_product'),
    path('product/<int:product_id>/', views.product_detail, name='product_detail'),
    path('product/<int:product_id>/edit/', views.edit_product, name='edit_product'),
    path('order/<int:order_id>/status/<str:status>/', views.update_order_status, name='update_order_status'),
]