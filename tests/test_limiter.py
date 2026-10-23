from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock
import pytest
from redis.exceptions import ConnectionError
from mailqueue.limiter import SlidingWindowLimiter


def test_production_minute_boundary(redis_client, rate_key):
    limiter = SlidingWindowLimiter(redis_client, key=rate_key)
    assert limiter.capacity == 200
    assert limiter.window_ms == 60000
    permits = [limiter.acquire() for _ in range(201)]
    assert sum(p.allowed for p in permits) == 200
    assert not permits[-1].allowed
    assert 0 < permits[-1].wait_ms <= 60000
    assert redis_client.pttl(rate_key) > 0


def test_atomic_under_concurrent_clients(redis_client, rate_key):
    limiter = SlidingWindowLimiter(redis_client, key=rate_key)
    with ThreadPoolExecutor(max_workers=16) as pool:
        permits = list(pool.map(lambda _: limiter.acquire(), range(500)))
    assert sum(p.allowed for p in permits) == 200
    assert redis_client.zcard(rate_key) == 200


def test_exact_cutoff_is_pruned(redis_client, rate_key):
    now = redis_client.time()
    ms = now[0] * 1000 + now[1] // 1000
    redis_client.zadd(rate_key, {"expired": ms - 60000, "current": ms})
    limiter = SlidingWindowLimiter(redis_client, key=rate_key, capacity=2)
    assert limiter.acquire().allowed
    assert redis_client.zcard(rate_key) == 2


def test_redis_error_propagates():
    client = Mock()
    client.register_script.return_value.side_effect = ConnectionError("offline")
    with pytest.raises(ConnectionError):
        SlidingWindowLimiter(client).acquire()
