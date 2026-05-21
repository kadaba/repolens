from django.urls import path
from . import views

urlpatterns = [
    path('products/', views.product_list),
    path('products/<int:pk>/', views.product_detail),
    path('cart/', views.cart_view),
    path('cart/add/', views.cart_add),
    path('checkout/', views.checkout),
    path('orders/', views.order_list),
    path('orders/<int:pk>/', views.order_detail),
    path('coupons/apply/', views.apply_coupon),
]
