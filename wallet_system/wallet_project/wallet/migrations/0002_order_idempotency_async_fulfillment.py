from django.db import migrations, models
import django.db.models.deletion
import django.db.models.expressions
import uuid


class Migration(migrations.Migration):
    dependencies = [
        ("wallet", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="idempotency_key",
            field=models.CharField(blank=True, max_length=128, null=True),
        ),
        migrations.AddField(
            model_name="order",
            name="refunded",
            field=models.BooleanField(default=False),
        ),
        migrations.AddConstraint(
            model_name="order",
            constraint=models.UniqueConstraint(
                condition=models.Q(("idempotency_key__isnull", False)),
                fields=("client", "idempotency_key"),
                name="uniq_order_client_idempotency_key_not_null",
            ),
        ),
        migrations.CreateModel(
            name="FulfillmentJob",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("status", models.CharField(choices=[("pending", "Pending"), ("processing", "Processing"), ("completed", "Completed"), ("failed", "Failed")], default="pending", max_length=20)),
                ("attempts", models.PositiveIntegerField(default=0)),
                ("last_error", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("order", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="fulfillment_job", to="wallet.order")),
            ],
        ),
        migrations.CreateModel(
            name="OrderEvent",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("event_type", models.CharField(max_length=64)),
                ("payload", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("order", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="events", to="wallet.order")),
            ],
        ),
    ]
