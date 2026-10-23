import uuid
import django.utils.timezone
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = [
        migrations.CreateModel(
            name="EmailJob",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("idempotency_key", models.CharField(max_length=128, unique=True)),
                ("recipient", models.EmailField(max_length=254)),
                ("subject", models.CharField(max_length=200)),
                ("body", models.TextField()),
                (
                    "state",
                    models.CharField(
                        choices=[("pending", "Pending"), ("sent", "Sent"), ("dead", "Dead")],
                        default="pending",
                        max_length=10,
                    ),
                ),
                ("failures", models.PositiveIntegerField(default=0)),
                ("last_error", models.TextField(blank=True)),
                ("next_attempt_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("lease_until", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("sent_at", models.DateTimeField(blank=True, null=True)),
            ],
            options={
                "indexes": [
                    models.Index(
                        fields=["state", "next_attempt_at"], name="mailqueue_e_state_685b91_idx"
                    )
                ]
            },
        ),
        migrations.CreateModel(
            name="Delivery",
            fields=[
                (
                    "job",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        primary_key=True,
                        serialize=False,
                        to="mailqueue.emailjob",
                    ),
                ),
                ("accepted_at", models.DateTimeField(auto_now_add=True)),
            ],
        ),
        migrations.CreateModel(
            name="DeadLetter",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("reason", models.TextField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "job",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE, to="mailqueue.emailjob"
                    ),
                ),
            ],
        ),
    ]
