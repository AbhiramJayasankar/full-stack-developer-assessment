import os
import uuid
import pytest
from redis import Redis
from redis.exceptions import RedisError


@pytest.fixture
def redis_client():
    client = Redis.from_url(
        os.environ.get("TEST_REDIS_URL", "redis://127.0.0.1:6379/15"),
        socket_connect_timeout=2,
        socket_timeout=2,
    )
    try:
        client.ping()
    except RedisError as exc:
        pytest.fail(
            f"Real Redis required: run docker compose up -d --wait redis. {type(exc).__name__}"
        )
    yield client
    client.close()


@pytest.fixture
def rate_key(redis_client):
    key = f"assessment:test:{uuid.uuid4()}:rate"
    yield key
    redis_client.delete(key)


@pytest.fixture(scope="session")
def django_db_modify_db_settings(django_db_modify_db_settings_parallel_suffix, tmp_path_factory):
    from django.conf import settings

    # File-backed DB is shared by the producer and Celery worker thread.
    settings.DATABASES["default"].setdefault("TEST", {})["NAME"] = str(
        tmp_path_factory.mktemp("database") / "test.sqlite3"
    )
