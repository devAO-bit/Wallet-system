from django.core.exceptions import ObjectDoesNotExist
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt

from .models import Client, Wallet, Order
from .serializers import CreditDebitSerializer, CreateOrderSerializer, OrderSerializer
from .services import credit_wallet, debit_wallet, create_order

@method_decorator(csrf_exempt, name='dispatch')
class AdminCreditWalletView(APIView):
    def post(self, request):
        serializer = CreditDebitSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            result = credit_wallet(
                client_id=str(serializer.validated_data['client_id']),
                amount=serializer.validated_data['amount'],
            )
            return Response(result, status=status.HTTP_200_OK)
        except Client.DoesNotExist:
            return Response({"error": "Client not found."}, status=status.HTTP_404_NOT_FOUND)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

@method_decorator(csrf_exempt, name='dispatch')
class AdminDebitWalletView(APIView):
    def post(self, request):
        serializer = CreditDebitSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            result = debit_wallet(
                client_id=str(serializer.validated_data['client_id']),
                amount=serializer.validated_data['amount'],
            )
            return Response(result, status=status.HTTP_200_OK)
        except Client.DoesNotExist:
            return Response({"error": "Client not found."}, status=status.HTTP_404_NOT_FOUND)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

@method_decorator(csrf_exempt, name='dispatch')
class CreateOrderView(APIView):
    def post(self, request):
        client_id = request.headers.get('client-id')
        if not client_id:
            return Response({"error": "client-id header is required."}, status=status.HTTP_400_BAD_REQUEST)

        serializer = CreateOrderSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            result = create_order(
                client_id=client_id,
                amount=serializer.validated_data['amount'],
            )
            return Response(result, status=status.HTTP_201_CREATED)
        except Client.DoesNotExist:
            return Response({"error": "Client not found."}, status=status.HTTP_404_NOT_FOUND)
        except (Wallet.DoesNotExist, ObjectDoesNotExist):
            return Response({"error": "Wallet not found for client."}, status=status.HTTP_404_NOT_FOUND)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

@method_decorator(csrf_exempt, name='dispatch')
class OrderDetailView(APIView):
    def get(self, request, order_id):
        client_id = request.headers.get('client-id')
        if not client_id:
            return Response({"error": "client-id header is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            order = Order.objects.get(id=order_id, client_id=client_id)
            serializer = OrderSerializer(order)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except Order.DoesNotExist:
            return Response({"error": "Order not found."}, status=status.HTTP_404_NOT_FOUND)

@method_decorator(csrf_exempt, name='dispatch')
class WalletBalanceView(APIView):
    def get(self, request):
        client_id = request.headers.get('client-id')
        if not client_id:
            return Response({"error": "client-id header is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            wallet = Wallet.objects.get(client_id=client_id)
            return Response({"client_id": client_id, "balance": wallet.balance}, status=status.HTTP_200_OK)
        except Wallet.DoesNotExist:
            return Response({"error": "Wallet not found."}, status=status.HTTP_404_NOT_FOUND)