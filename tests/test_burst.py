"""Real broker, actual Celery retry messages, Redis Lua, and durable job records."""

from collections import deque
from threading import Event
import os
import time
import uuid
import pytest
from celery.contrib.testing.worker import start_worker
from config.celery import app
from mailqueue import provider
from mailqueue.limiter import SlidingWindowLimiter
from mailqueue.models import Delivery, EmailJob
from mailqueue.services import enqueue_email


@pytest.mark.django_db(transaction=True)
def test_500_jobs_no_loss_rate_limited_and_retried(redis_client, rate_key, settings, monkeypatch):
    broker = os.environ.get("TEST_REDIS_URL", "redis://127.0.0.1:6379/15")
    queue = f"assessment-test-{uuid.uuid4()}"
    settings.REDIS_URL = broker
    settings.EMAIL_RATE_KEY = rate_key
    window_ms = int(os.environ.get("TEST_RATE_WINDOW_MS", "1000"))
    settings.EMAIL_RATE_WINDOW_MS = window_ms  # Same Lua/cap; optionally test real time.
    settings.EMAIL_PROVIDER_URL = ""
    previous = {
        name: app.conf.get(name)
        for name in [
            "CELERY_BROKER_URL",
            "CELERY_RESULT_BACKEND",
            "CELERY_TASK_DEFAULT_QUEUE",
            "CELERY_TASK_ALWAYS_EAGER",
        ]
    }
    app.conf.update(
        CELERY_BROKER_URL=broker,
        CELERY_RESULT_BACKEND=broker,
        CELERY_TASK_DEFAULT_QUEUE=queue,
        CELERY_TASK_ALWAYS_EAGER=False,
    )
    timestamps = []
    failure_ids = []
    real_acquire = SlidingWindowLimiter.acquire
    real_send = provider.send

    def record_acquire(self):
        permit = real_acquire(self)
        if permit.allowed:
            timestamps.append(permit.timestamp_ms)
        return permit

    def fail_once(job):
        if not failure_ids:
            failure_ids.append(job.pk)
            raise provider.TransientProviderError("intentional test failure")
        real_send(job)

    monkeypatch.setattr(SlidingWindowLimiter, "acquire", record_acquire)
    monkeypatch.setattr(provider, "send", fail_once)
    # A file DB and busy timeout avoid SQLite read/write lock conflicts between
    # the test producer and embedded worker. Submit all rows before consuming.
    jobs = []
    try:
        for i in range(500):
            jobs.append(
                enqueue_email(
                    idempotency_key=f"{queue}:{i}",
                    recipient="demo@example.com",
                    subject="Burst",
                    body="Test",
                ).pk
            )
        with start_worker(
            app,
            pool="solo",
            concurrency=1,
            perform_ping_check=False,
            queues=[queue],
            shutdown_timeout=15,
        ):
            deadline = time.monotonic() + 2 * window_ms / 1000 + 45
            while time.monotonic() < deadline:
                if EmailJob.objects.filter(pk__in=jobs, state="sent").count() == 500:
                    break
                Event().wait(0.1)
            assert EmailJob.objects.filter(pk__in=jobs).count() == 500
            assert EmailJob.objects.filter(pk__in=jobs, state="sent").count() == 500
            assert Delivery.objects.filter(job_id__in=jobs).count() == 500
        assert len(failure_ids) == 1
        assert EmailJob.objects.get(pk=failure_ids[0]).failures == 1
        assert len(timestamps) == 501
        active = deque()
        maximum = 0
        for timestamp in sorted(timestamps):
            while active and active[0] <= timestamp - window_ms:
                active.popleft()
            active.append(timestamp)
            maximum = max(maximum, len(active))
            assert len(active) <= 200
        assert max(timestamps) - min(timestamps) >= 2 * window_ms
        evidence_path = os.environ.get("QUEUE_EVIDENCE_PATH")
        if evidence_path:
            import json
            from pathlib import Path

            Path(evidence_path).write_text(
                json.dumps(
                    {
                        "jobs_submitted": 500,
                        "jobs_sent": 500,
                        "durable_deliveries": 500,
                        "provider_attempts": len(timestamps),
                        "intentional_failures_retried": 1,
                        "capacity": 200,
                        "window_ms": window_ms,
                        "max_attempts_in_rolling_window": maximum,
                        "elapsed_admission_ms": max(timestamps) - min(timestamps),
                        "admission_timestamps_ms": sorted(timestamps),
                    },
                    indent=2,
                )
                + "\n"
            )
    finally:
        app.conf.update(**previous)
        redis_client.delete(queue, rate_key)
