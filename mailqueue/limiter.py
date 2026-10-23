from dataclasses import dataclass
from uuid import uuid4
from django.conf import settings
from redis import Redis

# Redis TIME removes clock skew between workers. All pruning, checking, adding,
# and TTL updates execute atomically in one Lua invocation on the primary.
SLIDING_WINDOW = """
local t = redis.call('TIME')
local now = tonumber(t[1]) * 1000 + math.floor(tonumber(t[2]) / 1000)
local window = tonumber(ARGV[1])
local capacity = tonumber(ARGV[2])
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', now - window)
if redis.call('ZCARD', KEYS[1]) < capacity then
    redis.call('ZADD', KEYS[1], now, ARGV[3])
    redis.call('PEXPIRE', KEYS[1], window)
    return {1, 0, now}
end
local oldest = redis.call('ZRANGE', KEYS[1], 0, 0, 'WITHSCORES')
return {0, math.max(1, tonumber(oldest[2]) + window - now), now}
"""


@dataclass(frozen=True)
class Permit:
    allowed: bool
    wait_ms: int
    timestamp_ms: int


class SlidingWindowLimiter:
    def __init__(self, client=None, key=None, capacity=None, window_ms=None):
        self.client = (
            client
            if client is not None
            else Redis.from_url(settings.REDIS_URL, socket_connect_timeout=2, socket_timeout=2)
        )
        self.key = key or settings.EMAIL_RATE_KEY
        self.capacity = capacity if capacity is not None else settings.EMAIL_RATE_CAPACITY
        self.window_ms = window_ms if window_ms is not None else settings.EMAIL_RATE_WINDOW_MS
        if self.capacity <= 0 or self.window_ms <= 0:
            raise ValueError("Capacity and window must be positive")
        self.script = self.client.register_script(SLIDING_WINDOW)

    def acquire(self):
        # Unique per attempt: retries must consume another provider-call permit.
        result = self.script(keys=[self.key], args=[self.window_ms, self.capacity, str(uuid4())])
        return Permit(bool(result[0]), int(result[1]), int(result[2]))
