from datetime import timedelta
from unittest.mock import patch
import pytest
from celery.exceptions import Retry
from django.utils import timezone
from redis.exceptions import ConnectionError
from mailqueue import provider
from mailqueue.limiter import Permit
from mailqueue.models import DeadLetter, Delivery, EmailJob
from mailqueue.services import enqueue_email
from mailqueue.tasks import deliver_email, dispatch_pending

pytestmark = pytest.mark.django_db


def job(**kwargs):
    return EmailJob.objects.create(
        idempotency_key=kwargs.pop("key", "test"),
        recipient="test@example.com",
        subject="Test",
        body="Hello",
        **kwargs,
    )


def test_idempotent_enqueue_and_broker_failure(django_capture_on_commit_callbacks):
    with patch("mailqueue.services.publish") as publish:
        with django_capture_on_commit_callbacks(execute=True):
            a = enqueue_email(
                idempotency_key="same", recipient="a@example.com", subject="A", body="Body"
            )
            b = enqueue_email(
                idempotency_key="same", recipient="a@example.com", subject="A", body="Body"
            )
    publish.assert_called_once_with(a.pk)
    assert a.pk == b.pk
    assert EmailJob.objects.count() == 1


def test_publish_failure_keeps_outbox():
    from mailqueue.services import publish

    j = job()
    with patch.object(deliver_email, "apply_async", side_effect=ConnectionError("offline")):
        publish(j.pk)
    assert EmailJob.objects.get(pk=j.pk).state == "pending"
    with patch("mailqueue.services.publish") as send:
        dispatch_pending()
    send.assert_called_once_with(j.pk)


def test_redis_failure_is_closed():
    j = job()
    with (
        patch("mailqueue.tasks.SlidingWindowLimiter") as limiter,
        patch("mailqueue.tasks.provider.send") as send,
    ):
        limiter.return_value.acquire.side_effect = ConnectionError("offline")
        with pytest.raises(Retry):
            deliver_email.run(str(j.pk))
    send.assert_not_called()
    j.refresh_from_db()
    assert j.state == "pending" and j.failures == 0 and j.lease_until is None


def test_permanent_failure_dead_letters_atomically():
    j = job()
    with (
        patch("mailqueue.tasks.SlidingWindowLimiter") as limiter,
        patch(
            "mailqueue.tasks.provider.send", side_effect=provider.PermanentProviderError("HTTP 400")
        ),
    ):
        limiter.return_value.acquire.return_value = Permit(True, 0, 0)
        assert deliver_email.run(str(j.pk)) == "dead"
    j.refresh_from_db()
    assert j.state == "dead"
    assert DeadLetter.objects.get(job=j).reason == "HTTP 400"


def test_retry_exhaustion_and_backoff():
    j = job()
    delays = []
    with (
        patch("mailqueue.tasks.SlidingWindowLimiter") as limiter,
        patch(
            "mailqueue.tasks.provider.send", side_effect=provider.TransientProviderError("HTTP 503")
        ),
        patch.object(deliver_email, "retry", side_effect=Retry) as retry,
    ):
        limiter.return_value.acquire.return_value = Permit(True, 0, 0)
        for failure in range(1, 5):
            with pytest.raises(Retry):
                deliver_email.run(str(j.pk))
            delays.append(retry.call_args.kwargs["countdown"])
            j.refresh_from_db()
            assert j.failures == failure
            assert j.next_attempt_at > timezone.now()
            EmailJob.objects.filter(pk=j.pk).update(
                next_attempt_at=timezone.now() - timedelta(seconds=1)
            )
        assert deliver_email.run(str(j.pk)) == "dead"
    assert all(2 ** (i + 1) <= delay <= 2 ** (i + 1) + 0.25 for i, delay in enumerate(delays))
    assert DeadLetter.objects.filter(job=j).count() == 1


def test_crash_after_provider_acceptance_and_lease_recovery():
    j = job(lease_until=timezone.now() + timedelta(seconds=45))
    provider.send(j)  # Crash here leaves accepted delivery but no sent-state commit.
    assert deliver_email.run(str(j.pk)) == "not-due-or-already-claimed"
    EmailJob.objects.filter(pk=j.pk).update(lease_until=timezone.now() - timedelta(seconds=1))
    with patch("mailqueue.tasks.SlidingWindowLimiter") as limiter:
        limiter.return_value.acquire.return_value = Permit(True, 0, 0)
        assert deliver_email.run(str(j.pk)) == "sent"
        assert deliver_email.run(str(j.pk)) == "not-due-or-already-claimed"
    assert Delivery.objects.filter(job=j).count() == 1
