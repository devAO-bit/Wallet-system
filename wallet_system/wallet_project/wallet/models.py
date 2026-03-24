from django.db import models
from django.db.models import Q
import uuid


class Client(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    email = models.EmailField(unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.id})"


class Wallet(models.Model):
    id = models.BigAutoField(primary_key=True)
    client = models.OneToOneField(Client, on_delete=models.CASCADE, related_name='wallet')
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Wallet({self.client_id}) = {self.balance}"


class LedgerEntry(models.Model):
    CREDIT = 'credit'
    DEBIT = 'debit'
    TRANSACTION_TYPES = [(CREDIT, 'Credit'), (DEBIT, 'Debit')]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE, related_name='ledger_entries')
    transaction_type = models.CharField(max_length=10, choices=TRANSACTION_TYPES)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    balance_after = models.DecimalField(max_digits=12, decimal_places=2)
    description = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.transaction_type} {self.amount} on wallet {self.wallet_id}"


class Order(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_FULFILLED = 'fulfilled'
    STATUS_FAILED = 'failed'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_FULFILLED, 'Fulfilled'),
        (STATUS_FAILED, 'Failed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='orders')
    idempotency_key = models.CharField(max_length=128, blank=True, null=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    fulfillment_id = models.CharField(max_length=255, blank=True, null=True)
    refunded = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Order({self.id}) - {self.status}"

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["client", "idempotency_key"],
                condition=Q(idempotency_key__isnull=False),
                name="uniq_order_client_idempotency_key_not_null",
            )
        ]


class FulfillmentJob(models.Model):
    STATUS_PENDING = "pending"
    STATUS_PROCESSING = "processing"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_PROCESSING, "Processing"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_FAILED, "Failed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name="fulfillment_job")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    attempts = models.PositiveIntegerField(default=0)
    last_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"FulfillmentJob({self.order_id}) - {self.status}"


class OrderEvent(models.Model):
    EVENT_ORDER_CREATED = "order_created"
    EVENT_FULFILLMENT_QUEUED = "fulfillment_queued"
    EVENT_FULFILLMENT_ATTEMPT = "fulfillment_attempt"
    EVENT_FULFILLMENT_SUCCESS = "fulfillment_success"
    EVENT_FULFILLMENT_FAILURE = "fulfillment_failure"
    EVENT_REFUND_ISSUED = "refund_issued"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="events")
    event_type = models.CharField(max_length=64)
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"OrderEvent({self.order_id}) - {self.event_type}"