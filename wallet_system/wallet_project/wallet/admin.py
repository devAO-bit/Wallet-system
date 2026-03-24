from django.contrib import admin
from .models import Client, Wallet, LedgerEntry, Order

admin.site.register(Client)
admin.site.register(Wallet)
admin.site.register(LedgerEntry)
admin.site.register(Order)