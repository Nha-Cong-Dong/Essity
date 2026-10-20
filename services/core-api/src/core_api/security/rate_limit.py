"""Fixed-window rate limits on Redis (T1.6, ADR-0014).

A rule allows `limit` hits per `window` for each key (an email, an IP...). Time is cut into
windows of that length; each window has its own counter, which Redis deletes on its own.

Keys are hashed before they reach Redis: emails and IPs are never stored there in clear.
If Redis cannot be reached the limiter refuses (HTTP 503) rather than letting everything
through: it is what stops password guessing on login.
"""

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from redis import Redis
from redis.exceptions import RedisError

from core_api.clients.redis import get_redis

KEY_PREFIX = "ratelimit"

# DECR, but never below zero, and never on a counter that has already expired.
_REFUND = """
local count = tonumber(redis.call('GET', KEYS[1]) or '0')
if count > 0 then return redis.call('DECR', KEYS[1]) end
return 0
"""


@dataclass(frozen=True)
class RateLimit:
    name: str  # part of the Redis key: one counter space per rule
    limit: int
    window: timedelta


@dataclass(frozen=True)
class Cooldown:
    name: str
    period: timedelta


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    retry_after_seconds: int  # until the current window ends
    redis_key: str = ""  # the window's counter that was hit, for `refund`


class RateLimitedError(Exception):
    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__("rate limited")
        self.retry_after_seconds = retry_after_seconds


class RateLimiterUnavailableError(Exception):
    """Redis did not answer: the limiter refuses instead of allowing."""


def _utcnow() -> datetime:
    return datetime.now(UTC)


class RateLimiter:
    def __init__(self, redis: Redis, now: Callable[[], datetime] = _utcnow) -> None:
        self.redis = redis
        self.now = now

    def _window(self, rule: RateLimit, key: str) -> tuple[str, int]:
        """Redis key of the current window, and seconds until it ends."""
        seconds = int(rule.window.total_seconds())
        moment = int(self.now().timestamp())
        index = moment // seconds
        digest = hashlib.sha256(key.encode()).hexdigest()
        return f"{KEY_PREFIX}:{rule.name}:{digest}:{index}", (index + 1) * seconds - moment

    def hit(self, rule: RateLimit, key: str) -> RateLimitResult:
        """Count one attempt and say whether it is within the limit."""
        redis_key, remaining = self._window(rule, key)
        try:
            # One transaction: the counter can never exist without its expiry.
            pipe = self.redis.pipeline(transaction=True)  # pyright: ignore[reportUnknownMemberType]
            pipe.incr(redis_key)
            pipe.expire(redis_key, int(rule.window.total_seconds()) * 2, nx=True)
            count = int(pipe.execute()[0])
        except RedisError as exc:
            raise RateLimiterUnavailableError from exc
        return RateLimitResult(
            allowed=count <= rule.limit, retry_after_seconds=remaining, redis_key=redis_key
        )

    def refund(self, hit: RateLimitResult) -> None:
        """Give back one hit: the attempt turned out not to count (a correct password).

        Decrements the counter of the window the hit went into, not the current one: the
        window may have changed while the password was being hashed.
        """
        if not hit.redis_key:
            return
        try:
            self.redis.eval(_REFUND, 1, hit.redis_key)  # pyright: ignore[reportUnknownMemberType]
        except RedisError as exc:
            raise RateLimiterUnavailableError from exc

    def check(self, rule: RateLimit, key: str) -> RateLimitResult:
        """Whether one more attempt would be allowed, without counting it."""
        redis_key, remaining = self._window(rule, key)
        try:
            raw = self.redis.get(redis_key)
        except RedisError as exc:
            raise RateLimiterUnavailableError from exc
        count = int(raw) if raw is not None else 0  # pyright: ignore[reportArgumentType]
        return RateLimitResult(allowed=count < rule.limit, retry_after_seconds=remaining)

    def enforce_cooldown(self, rule: Cooldown, key: str) -> None:
        """At most one attempt per `period` for each key, counted from the last allowed one.

        Unlike `enforce`, no window boundary lets two attempts through a second apart: the
        key lives exactly `period` and is only set when absent. Raise RateLimitedError (HTTP
        429) with the time left.
        """
        digest = hashlib.sha256(key.encode()).hexdigest()
        redis_key = f"{KEY_PREFIX}:{rule.name}:{digest}"
        try:
            if self.redis.set(redis_key, 1, nx=True, ex=int(rule.period.total_seconds())):
                return
            remaining = int(self.redis.ttl(redis_key))  # pyright: ignore[reportArgumentType]
        except RedisError as exc:
            raise RateLimiterUnavailableError from exc
        raise RateLimitedError(max(remaining, 1))

    def enforce(self, rule: RateLimit, key: str) -> None:
        """Count one attempt; raise RateLimitedError (HTTP 429) when over the limit."""
        result = self.hit(rule, key)
        if not result.allowed:
            raise RateLimitedError(result.retry_after_seconds)


def install_rate_limit_handlers(app: FastAPI) -> None:
    """429 with Retry-After when limited; 503 when the limiter cannot decide."""

    async def limited(request: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, RateLimitedError)
        return JSONResponse(
            {"detail": "Too many attempts"},
            status_code=429,
            headers={"Retry-After": str(exc.retry_after_seconds)},
        )

    async def unavailable(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse({"detail": "Try again later"}, status_code=503)

    app.add_exception_handler(RateLimitedError, limited)
    app.add_exception_handler(RateLimiterUnavailableError, unavailable)


def get_rate_limiter() -> RateLimiter:
    """FastAPI dependency."""
    return RateLimiter(get_redis())
