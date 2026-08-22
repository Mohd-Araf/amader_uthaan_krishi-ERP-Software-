from django.urls import path
from . import views

urlpatterns = [
    path('shop/', views.shop, name='shop'),
    path('cart/', views.cart, name='cart'),
    path('add/<int:product_id>/', views.add_to_cart, name='add_to_cart'),
    path('confirm/', views.confirm_order, name='order_confirm'),
    path('confirm-page/', views.order_confirm, name='order_confirm_page'),
    path('product/<int:id>/', views.product_details, name='product_details'),




]