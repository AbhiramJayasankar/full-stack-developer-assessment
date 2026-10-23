# Section 2 — Rate-limited async job queue

## Choice and alternatives

Celery + Redis is the required implementation and fits an independently scalable worker fleet: Celery supplies routing, late acknowledgements, retries and worker supervision; Redis provides broker transport and a shared atomic limiter. Costs include Redis durability configuration, at-least-once semantics, and operating beat plus workers. Celery's per-worker `rate_limit` would multiply capacity with worker count, so it cannot enforce this provider-wide limit.

Django Q/Q2 offers a convenient Django-oriented scheduler and admin integration with fewer concepts for a small team, but still needs careful broker acknowledgement, crash recovery and a custom distributed limiter. It does not eliminate the provider-side duplicate problem. A custom database queue could atomically claim rows using PostgreSQL `select_for_update(skip_locked=True)` and avoid a broker, but requires implementing scheduling, retry visibility, worker lifecycle and observability. That is unnecessary maintenance for this task.

## Durable flow

1. `enqueue_email()` inserts an `EmailJob` in a database transaction, with a unique caller-supplied idempotency key. The row is the durable outbox. `transaction.on_commit()` publishes only after commit; broker errors leave the row pending.
2. A worker atomically claims a due row with a conditional `UPDATE`, setting a 45-second lease. Duplicate messages cannot simultaneously claim it. Hard task timeout is 30 seconds and HTTP timeout is bounded. Lease duration must exceed the maximum execution time.
3. The worker acquires a Redis permit, then calls the provider with the stable job UUID as its idempotency key. Only a successful provider response marks the job sent.
4. Transient errors (network, HTTP 429/5xx) increment a database failure counter and schedule `2**failures` seconds plus jitter, capped at 60 seconds. The fifth provider failure or an immediate permanent HTTP error atomically records a terminal state and `DeadLetter` row. Throttling and Redis outages do not consume the provider failure budget.
5. Beat scans due pending rows every ten seconds. This recovers a crash between commit and publication, a broker message loss, an expired lease, and a failed retry publication. It can publish duplicates; claims and provider idempotency handle them. Terminal jobs are retained for audit. There is deliberately no unreviewed automatic replay of dead letters.

A broker retry countdown and the persisted `next_attempt_at` are two recovery paths. An early message can be acknowledged without sending because beat will publish again when the database says it is due. Beat outages delay recovery; monitor its heartbeat and oldest pending age. For large fleets, add a database publication lease and batch dispatchers to reduce duplicate broker traffic. The current bounded scan is sufficient for a 2,000-job burst; it does not claim to provide strict fairness.

## Atomic sliding window

The Lua script uses Redis `TIME`, `ZREMRANGEBYSCORE`, `ZCARD`, `ZADD`, `PEXPIRE`, and `ZRANGE ... WITHSCORES`. It removes attempts at or before `now - 60000`, admits only when fewer than 200 remain, and returns the earliest next admission time when full. Every provider attempt gets a unique sorted-set member, including retries and failed requests. Lua makes prune/check/add/expire indivisible across workers. Redis server time avoids worker clock skew. The invariant is at most 200 admissions in each half-open rolling window `(t - 60s, t]`.

Fixed-window `INCR` + `EXPIRE` is cheaper but can admit 400 calls around a boundary. A token bucket allows bursts after idle periods; unless carefully constrained it does not represent a strict rolling-minute quota. The sliding window directly expresses the requested limit with only 200 active entries. The script returns a countdown; Celery schedules retries instead of blocking a worker with `time.sleep()`.

Redis errors **fail closed**: no provider call occurs. A five-second retry is scheduled and the database outbox remains recoverable. All workers sending for this provider account must share the same key. The Lua script runs on the Redis primary; this implementation is for standalone Redis, not a Redis Cluster broker.

## Crash and duplicate semantics

`CELERY_TASK_ACKS_LATE=True` (task attribute `acks_late`) acknowledges after execution; `CELERY_TASK_REJECT_ON_WORKER_LOST=True` (task attribute `reject_on_worker_lost`) asks the parent to requeue a message when a child is SIGKILL'd. `CELERY_WORKER_PREFETCH_MULTIPLIER=1` bounds reserved work. If the whole worker host dies, Redis restores unacknowledged messages after its 300-second visibility timeout. `CELERY_WORKER_CANCEL_LONG_RUNNING_TASKS_ON_CONNECTION_LOSS=True` reduces concurrent execution after broker reconnect. Database leases and beat can recover sooner than transport restoration.

If death happens after the provider accepts but before the sent-state commit, a later worker repeats the request with the same UUID. Exactly-once email delivery is impossible from local acknowledgements alone: the provider must honor idempotency keys for the entire retry/recovery retention period. The demo `Delivery` table uses a unique job key to simulate that contract. Without provider deduplication, the honest guarantee is at-least-once attempts with possible duplicate emails. A stale worker surviving beyond its lease could overlap a newer owner; enforced task timeouts and bounded I/O are required, and provider deduplication remains the final safeguard.

Compose enables Redis AOF with `appendfsync always` and `noeviction`. The database is the source of truth even if broker data is lost. A lost limiter key, a Redis primary rollback, or administrative deletion can erase quota history: AOF reduces that risk but does not prove quota continuity after catastrophic data loss. On such recovery, operators must pause sending for one full window before resuming, or restore trusted quota history. Permits limit admission times; arbitrary process pauses between admission and HTTP dispatch can shift actual arrival times. A strict provider-arrival guarantee needs a provider-enforced quota or centralized dispatch with conservative headroom.

## Verification and limits

The 500-job test uses a real Redis broker, real Lua, and Celery's embedded solo worker, with a one-second test window to avoid a two-minute test. It verifies no accepted job is lost, all attempts obey the rolling quota including a forced retry, and successful deliveries are deduplicated. The same 500-job test was also run with the production 60-second window; `evidence/queue-500-jobs.json` records all 501 admissions, 500 successful jobs, and a maximum rolling count of 200. A separate test checks 200 admissions and rejection 201 with the production 60-second default; concurrency is tested with multiple client threads. Lease expiry is simulated deterministically; an OS-level SIGKILL integration test is not claimed. SQLite is adequate for local single-worker operation; PostgreSQL is recommended for concurrent production updates and durable backups. Provider HTTP error strings are stored without email bodies or credentials; production logging and retention need a PII policy.
