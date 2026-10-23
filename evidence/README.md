Profiler evidence is generated from real django-silk SQL records with:

```sh
python manage.py migrate
python scripts/profile_orders.py
```

The generated `silk-queries.json` contains order count, before/after query counts,
and captured SQL. Open `/silk/` after running the server to inspect request details.
The regression test also asserts both query counts against Silk's recorded queries.

Measured for 250 orders: **251 queries before, 1 after**. See the committed
`silk-queries.json` for SQL examples and `tests.xml` for regression test results.
The real-time queue evidence is captured separately in `queue-500-jobs.json`;
its timestamps permit independently checking every rolling window.
