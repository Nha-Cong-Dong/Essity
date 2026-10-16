# redis-py's scan_iter/ttl are loosely typed; only these Redis-inspecting tests need it.
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false
"""T1.6: rate limiting on Redis. Runs on a real Redis (database 15, see conftest)."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from redis import Redis

from core_api.clients.redis import redis_from_url
from core_api.security.rate_limit import (
    RateLimit,
    RateLimiter,
    RateLimiterUnavailableError,
    install_rate_limit_handlers,
)

T0 = datetime(2026, 10, 16, 12, 0, 0, tzinfo=UTC)


class Clock:
    def __init__(self) -> None:
        self.now = T0

    def __call__(self) -> datetime:
        return self.now


def rule(limit: int = 3, window: timedelta = timedelta(minutes=15)) -> RateLimit:
    # A fresh name per test: tests share the Redis database and may run in any order.
    return RateLimit(name=f"test-{uuid.uuid4().hex}", limit=limit, window=window)


def test_hits_up_to_the_limit_are_allowed_then_refused(redis_client: Redis) -> None:
    limiter, limit = RateLimiter(redis_client, now=Clock()), rule(limit=3)
    results = [limiter.hit(limit, "alice@example.com") for _ in range(4)]
    assert [r.allowed for r in results] == [True, True, True, False]


def test_a_new_window_allows_again(redis_client: Redis) -> None:
    clock = Clock()
    limiter, limit = RateLimiter(redis_client, now=clock), rule(limit=1)
    assert limiter.hit(limit, "k").allowed
    assert not limiter.hit(limit, "k").allowed
    clock.now = T0 + limit.window
    assert limiter.hit(limit, "k").allowed


def test_retry_after_counts_down_to_the_end_of_the_window(redis_client: Redis) -> None:
    clock = Clock()
    limiter, limit = RateLimiter(redis_client, now=clock), rule(limit=1)
    limiter.hit(limit, "k")
    clock.now = T0 + timedelta(minutes=10)
    refused = limiter.hit(limit, "k")
    assert not refused.allowed
    assert refused.retry_after_seconds == 5 * 60


def test_keys_are_counted_separately(redis_client: Redis) -> None:
    limiter, limit = RateLimiter(redis_client, now=Clock()), rule(limit=1)
    assert limiter.hit(limit, "alice@example.com").allowed
    assert limiter.hit(limit, "bob@example.com").allowed


def test_check_does_not_count(redis_client: Redis) -> None:
    limiter, limit = RateLimiter(redis_client, now=Clock()), rule(limit=1)
    for _ in range(3):
        assert limiter.check(limit, "k").allowed
    limiter.hit(limit, "k")
    assert not limiter.check(limit, "k").allowed


def test_redis_never_stores_the_raw_key(redis_client: Redis) -> None:
    limiter, limit = RateLimiter(redis_client, now=Clock()), rule()
    limiter.hit(limit, "alice@example.com")
    keys = [k.decode() for k in redis_client.scan_iter(f"ratelimit:{limit.name}:*")]
    assert len(keys) == 1
    assert "alice" not in keys[0]


def test_counters_expire_on_their_own(redis_client: Redis) -> None:
    limiter, limit = RateLimiter(redis_client, now=Clock()), rule(window=timedelta(seconds=90))
    limiter.hit(limit, "k")
    [key] = list(redis_client.scan_iter(f"ratelimit:{limit.name}:*"))
    assert 0 < redis_client.ttl(key) <= 2 * 90


def test_unreachable_redis_refuses_instead_of_allowing() -> None:
    # Fail closed: this protects login against password guessing.
    dead = redis_from_url("redis://127.0.0.1:1/0", timeout=0.2)
    with pytest.raises(RateLimiterUnavailableError):
        RateLimiter(dead, now=Clock()).hit(rule(), "k")


# --- HTTP ------------------------------------------------------------------------------------


def make_app(limiter: RateLimiter, limit: RateLimit) -> FastAPI:
    app = FastAPI()
    install_rate_limit_handlers(app)

    @app.post("/login")
    def login(request: Request) -> dict[str, str]:
        limiter.enforce(limit, "alice@example.com")
        return {"status": "ok"}

    _ = login
    return app


def test_over_the_limit_is_a_429_with_retry_after(redis_client: Redis) -> None:
    client = TestClient(make_app(RateLimiter(redis_client, now=Clock()), rule(limit=2)))
    assert [client.post("/login").status_code for _ in range(3)] == [200, 200, 429]
    refused = client.post("/login")
    assert refused.status_code == 429
    assert int(refused.headers["Retry-After"]) == 15 * 60


def test_unreachable_redis_is_a_503() -> None:
    dead = redis_from_url("redis://127.0.0.1:1/0", timeout=0.2)
    client = TestClient(make_app(RateLimiter(dead, now=Clock()), rule()))
    assert client.post("/login").status_code == 503
