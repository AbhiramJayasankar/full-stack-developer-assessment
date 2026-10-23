from datetime import timedelta
import random
from celery import shared_task
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from redis.exceptions import RedisError
from . import provider
from .limiter import SlidingWindowLimiter
from .models import DeadLetter, EmailJob

LEASE_SECONDS = 45  # Greater than the worker hard time limit (30s).
MAX_FAILURES = 5


def release(job_id, delay, **updates):
    EmailJob.objects.filter(pk=job_id, state=EmailJob.State.PENDING).update(
        lease_until=None, next_attempt_at=timezone.now() + timedelta(seconds=delay), **updates
    )


@shared_task(bind=True, max_retries=None, name="mailqueue.tasks.deliver_email")
def deliver_email(self, job_id):
    now = timezone.now()
    claimed = (
        EmailJob.objects.filter(pk=job_id, state=EmailJob.State.PENDING, next_attempt_at__lte=now)
        .filter(Q(lease_until__isnull=True) | Q(lease_until__lte=now))
        .update(lease_until=now + timedelta(seconds=LEASE_SECONDS))
    )
    if not claimed:
        return "not-due-or-already-claimed"
    job = EmailJob.objects.get(pk=job_id)
    try:
        permit = SlidingWindowLimiter().acquire()
    except RedisError:
        release(job_id, 5)
        raise self.retry(countdown=5)
    if not permit.allowed:
        delay = permit.wait_ms / 1000 + random.uniform(0.01, 0.1)
        release(job_id, delay)
        raise self.retry(countdown=delay)
    try:
        provider.send(job)
    except (provider.TransientProviderError, provider.PermanentProviderError) as exc:
        failures = job.failures + 1
        reason = str(exc)[:500]
        if isinstance(exc, provider.PermanentProviderError) or failures >= MAX_FAILURES:
            with transaction.atomic():
                EmailJob.objects.filter(pk=job_id).update(
                    state=EmailJob.State.DEAD,
                    failures=failures,
                    last_error=reason,
                    lease_until=None,
                )
                DeadLetter.objects.get_or_create(job_id=job_id, defaults={"reason": reason})
            return "dead"
        delay = min(2**failures, 60) + random.uniform(0, 0.25)
        release(job_id, delay, failures=failures, last_error=reason)
        raise self.retry(countdown=delay, exc=exc)
    EmailJob.objects.filter(pk=job_id).update(
        state=EmailJob.State.SENT, sent_at=timezone.now(), lease_until=None, last_error=""
    )
    return "sent"


@shared_task(name="mailqueue.tasks.dispatch_pending")
def dispatch_pending():
    from .services import publish

    now = timezone.now()
    ids = (
        EmailJob.objects.filter(state=EmailJob.State.PENDING, next_attempt_at__lte=now)
        .filter(Q(lease_until__isnull=True) | Q(lease_until__lte=now))
        .order_by("next_attempt_at")
        .values_list("pk", flat=True)[:2000]
    )
    for job_id in list(ids):
        publish(job_id)
