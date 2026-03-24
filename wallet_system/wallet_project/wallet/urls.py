from django.urls import path
from .views import (
    AdminCreditWalletView,
    AdminDebitWalletView,
    CreateOrderView,
    OrderDetailView,
    WalletBalanceView,
)

# urls.py - cleaner version
urlpatterns = [
    path('admin/wallet/credit', AdminCreditWalletView.as_view(), name='admin-credit'),
    path('admin/wallet/debit', AdminDebitWalletView.as_view(), name='admin-debit'),
    path('orders', CreateOrderView.as_view(), name='create-order'),
    path('orders/<uuid:order_id>', OrderDetailView.as_view(), name='order-detail'),
    path('wallet/balance', WalletBalanceView.as_view(), name='wallet-balance'),
]