# Full-stack developer assessment

This repo contains an order-summary query fix and a rate-limited email queue, built with Django, Celery and Redis. The incident write-up and architecture answers are in [ANSWERS.md](ANSWERS.md); queue decisions and trade-offs are in [DESIGN.md](DESIGN.md).

The examples use synthetic orders. Email delivery is simulated locally, so you can run everything without provider credentials or sending mail.

## Run locally

Prerequisites: Python 3.12+, Docker with Compose (or an existing Redis server), and package-index access.

```sh
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
docker compose up -d --wait redis
python manage.py migrate
python manage.py check
pytest -q
python scripts/profile_orders.py
python manage.py runserver
```

Windows: activate with `.venv\Scripts\activate`. If Redis is already running on localhost:6379, omit Compose. Set `REDIS_URL` to override the application Redis URL and `TEST_REDIS_URL` to override the test URL (default: localhost database 15). Tests use unique keys and do not flush a shared database.

Open http://127.0.0.1:8000/api/orders/summary/ and http://127.0.0.1:8000/silk/. The profiler script creates 250 orders if the database is empty and writes SQL counts to `evidence/silk-queries.json`. The intentionally broken endpoint is `/demo/orders/broken/`. These unauthenticated demo endpoints expose synthetic orders only. A production API must authenticate and filter to the current account, and remove the broken endpoint and public Silk access.

## Run the queue

After migration, run these in separate activated terminals:

```sh
celery -A config worker --loglevel=INFO --concurrency=1
```

```sh
celery -A config beat --loglevel=INFO
```

```sh
python scripts/submit_jobs.py --count 500
python scripts/queue_status.py
docker compose exec redis redis-cli ZCARD email:provider:sliding-window
```

Beat is required to recover expired leases and database outbox jobs after crashes or broker outages. The provider's global limit is **200 attempts in every rolling 60 seconds**, across workers. Five hundred successful sends need at least two window boundaries; retries consume additional permits. SQLite is for a single-worker local demo. Use PostgreSQL and measured concurrency for production.

The default tests submit 500 jobs through a real Celery worker and Redis broker. They shorten the window to one second to keep the suite quick, while keeping the capacity at 200. They check that every job finishes, one deliberate failure retries, and no rolling window exceeds the limit. Other tests cover Redis outages, dead letters, duplicate messages and expired leases. The full-minute test below uses the production window.

To connect a real provider, set `EMAIL_PROVIDER_URL` to an adapter endpoint accepting JSON `to`, `subject`, `body` and the `Idempotency-Key` header. It must guarantee deduplication by that key; see DESIGN.md. Use HTTPS with an authenticated adapter in production. Never commit credentials. Local Django generates an ephemeral development secret unless `DJANGO_SECRET_KEY` is supplied.

## Verification

`python manage.py check`, migration drift detection, and the full test suite pass.
Measured Silk evidence is in [evidence/silk-queries.json](evidence/silk-queries.json):
250 orders take **251 queries before the fix and 1 after**. Test results are in
[evidence/tests.xml](evidence/tests.xml). All dependencies, including transitive
packages, are pinned by `requirements.lock` via the requirements constraints file.

The full-duration test also passed with the production limit: **500 jobs sent,
501 attempts (one retry), at most 200 admissions in any rolling 60 seconds**.
The timestamp trace is in [evidence/queue-500-jobs.json](evidence/queue-500-jobs.json).
To repeat it (about two minutes):

```sh
TEST_RATE_WINDOW_MS=60000 QUEUE_EVIDENCE_PATH=evidence/queue-500-jobs.json pytest tests/test_burst.py -q
```

The fast default suite uses the same Redis Lua code with a one-second window.
GitHub Actions repeats setup, Django checks, migration drift detection and tests
in a clean runner with real Redis. No external provider credentials are needed.

## Recorded walkthrough

[Watch or download the 5-minute 30-second queue walkthrough](https://github.com/AbhiramJayasankar/full-stack-developer-assessment/raw/refs/heads/main/evidence/queue-walkthrough.mp4).

This is a live cloud capture with Kokoro neural narration (`af_heart`) and on-screen captions. The voice is synthesized offline. It starts from a fresh shell, queues 500 jobs, and shows the worker, Redis state, full 60-second rate windows, and one deliberate HTTP 503 followed by a successful retry. The run uses an isolated demo database and Redis database 14. The provider simulates acceptance; no real email is sent.

The video, [subtitles](evidence/queue-walkthrough.srt), and [timestamp report](evidence/queue-recording-report.json) are in `evidence/`. The report is checked for 500 sent jobs, 500 durable deliveries, one provider failure, and no more than 200 admissions in any rolling minute.

To try the one-time failure locally, run `python scripts/demo_provider.py` in another terminal and set `EMAIL_PROVIDER_URL=http://127.0.0.1:8765` in the worker's terminal before starting Celery. The simulator rejects its first request with HTTP 503 and deduplicates later requests by job ID. Use `python scripts/queue_status.py` to check progress without printing email addresses or bodies.
