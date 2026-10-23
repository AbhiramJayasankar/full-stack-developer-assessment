import uuid
from django.db import models
from django.utils import timezone


class EmailJob(models.Model):
    class State(models.TextChoices):
        PENDING = "pending"
        SENT = "sent"
        DEAD = "dead"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    idempotency_key = models.CharField(max_length=128, unique=True)
    recipient = models.EmailField()
    subject = models.CharField(max_length=200)
    body = models.TextField()
    state = models.CharField(max_length=10, choices=State.choices, default=State.PENDING)
    failures = models.PositiveIntegerField(default=0)
    last_error = models.TextField(blank=True)
    next_attempt_at = models.DateTimeField(default=timezone.now)
    lease_until = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["state", "next_attempt_at"], name="mailqueue_e_state_685b91_idx")
        ]


class Delivery(models.Model):
    """Local provider simulator: durable deduplication of provider acceptance."""

    job = models.OneToOneField(EmailJob, primary_key=True, on_delete=models.CASCADE)
    accepted_at = models.DateTimeField(auto_now_add=True)


class DeadLetter(models.Model):
    job = models.OneToOneField(EmailJob, on_delete=models.CASCADE)
    reason = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
