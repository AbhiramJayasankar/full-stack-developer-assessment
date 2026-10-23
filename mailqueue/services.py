import logging
from django.db import transaction
from .models import EmailJob

logger = logging.getLogger(__name__)


def publish(job_id):
    from .tasks import deliver_email

    try:
        deliver_email.apply_async(args=[str(job_id)], retry=False)
    except Exception:
        # Accepted jobs remain durable; beat publishes them once Redis recovers.
        logger.exception("Broker publish failed; job remains in database outbox")


def enqueue_email(*, idempotency_key, recipient, subject, body):
    with transaction.atomic():
        job, created = EmailJob.objects.get_or_create(
            idempotency_key=idempotency_key,
            defaults={"recipient": recipient, "subject": subject, "body": body},
        )
        if created:
            transaction.on_commit(lambda: publish(job.pk))
    return job
