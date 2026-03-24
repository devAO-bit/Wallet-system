import logging
import requests
from decimal import Decimal

from django.db import transaction

from .models import Client, Wallet, LedgerEntry, Order

logger = logging.getLogger(__name__)

FULFILLMENT_API_URL = "https://jsonplaceholder.typicode.com/posts"


def get_or_create_wallet(client: Client) -> Wallet:
    wallet, _ = Wallet.objects.get_or_create(client=client)
    return wallet


def credit_wallet(client_id: str, amount: Decimal) -> dict:
    """
    Credits the wallet for the given client.
    Returns updated balance info.
    Raises: Client.DoesNotExist, ValueError
    """
    if amount <= 0:
        raise ValueError("Credit amount must be positive.")

    with transaction.atomic():
        client = Client.objects.select_for_update().get(id=client_id)
        wallet, _ = Wallet.objects.get_or_create(client=client)
        # Re-fetch wallet with lock
        wallet = Wallet.objects.select_for_update().get(client=client)
        wallet.balance += amount
        wallet.save()

        LedgerEntry.objects.create(
            wallet=wallet,
            transaction_type=LedgerEntry.CREDIT,
            amount=amount,
            balance_after=wallet.balance,
            description="Admin credit",
        )

    return {"client_id": str(client.id), "balance": wallet.balance}


def debit_wallet(client_id: str, amount: Decimal) -> dict:
    """
    Debits the wallet for the given client if balance is sufficient.
    Raises: Client.DoesNotExist, ValueError
    """
    if amount <= 0:
        raise ValueError("Debit amount must be positive.")

    with transaction.atomic():
        client = Client.objects.select_for_update().get(id=client_id)
        wallet, _ = Wallet.objects.get_or_create(client=client)
        # Re-fetch wallet with lock (works for both existing and newly created wallets)
        wallet = Wallet.objects.select_for_update().get(client=client)

        if wallet.balance < amount:
            raise ValueError("Insufficient wallet balance.")

        wallet.balance -= amount
        wallet.save()

        LedgerEntry.objects.create(
            wallet=wallet,
            transaction_type=LedgerEntry.DEBIT,
            amount=amount,
            balance_after=wallet.balance,
            description="Admin debit",
        )

    return {"client_id": str(client.id), "balance": wallet.balance}


def create_order(client_id: str, amount: Decimal) -> dict:
    """
    Atomically deducts the amount from wallet and creates an order.
    Then calls the fulfillment API and stores the returned ID.
    Raises: Client.DoesNotExist, ValueError
    """
    if amount <= 0:
        raise ValueError("Order amount must be positive.")

    with transaction.atomic():
        client = Client.objects.select_for_update().get(id=client_id)
        wallet, _ = Wallet.objects.get_or_create(client=client)
        # Re-fetch wallet with lock (works for both existing and newly created wallets)
        wallet = Wallet.objects.select_for_update().get(client=client)

        if wallet.balance < amount:
            raise ValueError("Insufficient wallet balance.")

        wallet.balance -= amount
        wallet.save()

        LedgerEntry.objects.create(
            wallet=wallet,
            transaction_type=LedgerEntry.DEBIT,
            amount=amount,
            balance_after=wallet.balance,
            description="Order deduction",
        )

        order = Order.objects.create(
            client=client,
            amount=amount,
            status=Order.STATUS_PENDING,
        )

    # Call fulfillment API outside the DB transaction to avoid holding locks
    fulfillment_id = _call_fulfillment_api(str(client.id), str(order.id))

    # Update the order with the fulfillment result
    if fulfillment_id:
        order.status = Order.STATUS_FULFILLED
        order.fulfillment_id = fulfillment_id
    else:
        order.status = Order.STATUS_FAILED

    order.save()

    return {
        "order_id": str(order.id),
        "client_id": str(client.id),
        "amount": order.amount,
        "status": order.status,
        "fulfillment_id": order.fulfillment_id,
    }


def _call_fulfillment_api(client_id: str, order_id: str) -> str | None:
    """
    Calls the external fulfillment API.
    Returns the fulfillment ID on success, None on failure.
    """
    try:
        response = requests.post(
            FULFILLMENT_API_URL,
            json={"userId": client_id, "title": order_id},
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
        # jsonplaceholder returns the created object with an 'id'
        return str(data.get("id"))
    except requests.RequestException as e:
        logger.error("Fulfillment API call failed for order %s: %s", order_id, e)
        return None