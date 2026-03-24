from decimal import Decimal
from rest_framework import serializers
from .models import Order


class CreditDebitSerializer(serializers.Serializer):
    client_id = serializers.UUIDField()
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))


class CreateOrderSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))


class OrderSerializer(serializers.ModelSerializer):
    class Meta:
        model = Order
        fields = ['id', 'client_id', 'amount', 'status', 'fulfillment_id', 'created_at', 'updated_at']