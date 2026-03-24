import logging
import threading
import time
import json
from urllib import error as urllib_error
from urllib import request as urllib_request
from decimal import Decimal

from django.db import transaction

from .models import Client, Wallet, LedgerEntry, Order, FulfillmentJob, OrderEvent

logger = logging.getLogger(__name__)

FULFILLMENT_API_URL = "https://jsonplaceholder.typicode.com/posts"
MAX_FULFILLMENT_RETRIES = 3
BASE_BACKOFF_SECONDS = 1

# Lightweight circuit breaker state (process-local).
_circuit_lock = threading.Lock()
_circuit_consecutive_failures = 0
_circuit_open_until = 0.0
_circuit_failure_threshold = 5
_circuit_open_seconds = 30


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
    return _create_order_internal(client_id=client_id, amount=amount, idempotency_key=None)


def create_order_with_idempotency(client_id: str, amount: Decimal, idempotency_key: str) -> dict:
    """
    Same as create_order, but idempotent by (client_id, idempotency_key).
    """
    if not idempotency_key:
        raise ValueError("idempotency-key header is required.")
    return _create_order_internal(client_id=client_id, amount=amount, idempotency_key=idempotency_key)


def _create_order_internal(client_id: str, amount: Decimal, idempotency_key: str | None) -> dict:
    if amount <= 0:
        raise ValueError("Order amount must be positive.")

    with transaction.atomic():
        client = Client.objects.select_for_update().get(id=client_id)

        if idempotency_key:
            existing = Order.objects.filter(client=client, idempotency_key=idempotency_key).first()
            if existing:
                return _order_response(existing, idempotent_replay=True)

        wallet, _ = Wallet.objects.get_or_create(client=client)
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
            idempotency_key=idempotency_key,
            amount=amount,
            status=Order.STATUS_PENDING,
        )
        job = FulfillmentJob.objects.create(order=order, status=FulfillmentJob.STATUS_PENDING)
        _create_order_event(order, OrderEvent.EVENT_ORDER_CREATED, {"amount": str(amount)})
        _create_order_event(order, OrderEvent.EVENT_FULFILLMENT_QUEUED, {"job_id": str(job.id)})

        transaction.on_commit(lambda: _enqueue_fulfillment_job(str(job.id)))

    return _order_response(order, idempotent_replay=False)


def _enqueue_fulfillment_job(job_id: str) -> None:
    thread = threading.Thread(target=_process_fulfillment_job, args=(job_id,), daemon=True)
    thread.start()


def _process_fulfillment_job(job_id: str) -> None:
    try:
        job = FulfillmentJob.objects.select_related("order", "order__client").get(id=job_id)
    except FulfillmentJob.DoesNotExist:
        logger.error("Fulfillment job %s does not exist", job_id)
        return

    with transaction.atomic():
        job = FulfillmentJob.objects.select_for_update().get(id=job.id)
        if job.status in (FulfillmentJob.STATUS_COMPLETED, FulfillmentJob.STATUS_FAILED):
            return
        job.status = FulfillmentJob.STATUS_PROCESSING
        job.save(update_fields=["status", "updated_at"])

    order = job.order
    fulfillment_id, error = _call_fulfillment_api_with_retries(order)

    with transaction.atomic():
        locked_job = FulfillmentJob.objects.select_for_update().get(id=job.id)
        locked_order = Order.objects.select_for_update().get(id=order.id)

        if fulfillment_id:
            locked_order.status = Order.STATUS_FULFILLED
            locked_order.fulfillment_id = fulfillment_id
            locked_order.save(update_fields=["status", "fulfillment_id", "updated_at"])

            locked_job.status = FulfillmentJob.STATUS_COMPLETED
            locked_job.last_error = ""
            locked_job.save(update_fields=["status", "last_error", "updated_at"])
            _create_order_event(locked_order, OrderEvent.EVENT_FULFILLMENT_SUCCESS, {"fulfillment_id": fulfillment_id})
            return

        locked_order.status = Order.STATUS_FAILED
        locked_order.save(update_fields=["status", "updated_at"])

        locked_job.status = FulfillmentJob.STATUS_FAILED
        locked_job.last_error = error or "Fulfillment failed."
        locked_job.save(update_fields=["status", "last_error", "updated_at"])
        _create_order_event(locked_order, OrderEvent.EVENT_FULFILLMENT_FAILURE, {"error": locked_job.last_error})

    _refund_failed_order(order_id=str(order.id), reason=error or "Fulfillment failed after retries.")


def _call_fulfillment_api_with_retries(order: Order) -> tuple[str | None, str | None]:
    last_error = None
    for attempt in range(1, MAX_FULFILLMENT_RETRIES + 1):
        if _is_circuit_open():
            last_error = "Circuit breaker open for fulfillment provider."
            time.sleep(BASE_BACKOFF_SECONDS * attempt)
            continue

        with transaction.atomic():
            job = FulfillmentJob.objects.select_for_update().get(order=order)
            job.attempts = attempt
            job.save(update_fields=["attempts", "updated_at"])

        _create_order_event(order, OrderEvent.EVENT_FULFILLMENT_ATTEMPT, {"attempt": attempt})

        try:
            fulfillment_id = _call_fulfillment_api(str(order.client_id), str(order.id))
            _record_circuit_success()
            return fulfillment_id, None
        except (urllib_error.URLError, TimeoutError, ValueError) as exc:
            _record_circuit_failure()
            last_error = str(exc)
            logger.warning("Fulfillment attempt %s failed for order %s: %s", attempt, order.id, exc)
            if attempt < MAX_FULFILLMENT_RETRIES:
                time.sleep(BASE_BACKOFF_SECONDS * (2 ** (attempt - 1)))

    return None, last_error


def _call_fulfillment_api(client_id: str, order_id: str) -> str:
    """
    Calls the external fulfillment API.
    Returns the fulfillment ID on success.
    Raises urllib/network errors on failure.
    """
    payload = json.dumps({"userId": client_id, "title": order_id}).encode("utf-8")
    req = urllib_request.Request(
        FULFILLMENT_API_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib_request.urlopen(req, timeout=10) as response:
        if response.status < 200 or response.status >= 300:
            raise urllib_error.HTTPError(
                FULFILLMENT_API_URL, response.status, "Unexpected status code", response.headers, None
            )
        body = response.read().decode("utf-8")
    data = json.loads(body)
    fulfillment_id = data.get("id")
    if not fulfillment_id:
        raise ValueError("Fulfillment API response missing id.")
    return str(fulfillment_id)


def _refund_failed_order(order_id: str, reason: str) -> None:
    with transaction.atomic():
        order = Order.objects.select_for_update().get(id=order_id)
        if order.refunded:
            return

        wallet = Wallet.objects.select_for_update().get(client=order.client)
        wallet.balance += order.amount
        wallet.save(update_fields=["balance", "updated_at"])

        LedgerEntry.objects.create(
            wallet=wallet,
            transaction_type=LedgerEntry.CREDIT,
            amount=order.amount,
            balance_after=wallet.balance,
            description=f"Refund for failed fulfillment (order {order.id})",
        )

        order.refunded = True
        order.save(update_fields=["refunded", "updated_at"])
        _create_order_event(order, OrderEvent.EVENT_REFUND_ISSUED, {"reason": reason, "amount": str(order.amount)})


def _create_order_event(order: Order, event_type: str, payload: dict | None = None) -> None:
    OrderEvent.objects.create(order=order, event_type=event_type, payload=payload or {})


def _is_circuit_open() -> bool:
    with _circuit_lock:
        return time.time() < _circuit_open_until


def _record_circuit_success() -> None:
    global _circuit_consecutive_failures
    with _circuit_lock:
        _circuit_consecutive_failures = 0


def _record_circuit_failure() -> None:
    global _circuit_consecutive_failures, _circuit_open_until
    with _circuit_lock:
        _circuit_consecutive_failures += 1
        if _circuit_consecutive_failures >= _circuit_failure_threshold:
            _circuit_open_until = time.time() + _circuit_open_seconds
            _circuit_consecutive_failures = 0


def _order_response(order: Order, idempotent_replay: bool) -> dict:
    return {
        "order_id": str(order.id),
        "client_id": str(order.client_id),
        "amount": order.amount,
        "status": order.status,
        "fulfillment_id": order.fulfillment_id,
        "refunded": order.refunded,
        "idempotent_replay": idempotent_replay,
    }