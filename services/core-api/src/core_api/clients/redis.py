"""The Redis connection of core-api (rate limits now; more later)."""

from functools import lru_cache

from opentelemetry.instrumentation.redis import (  # pyright: ignore[reportMissingTypeStubs]
    RedisInstrumentor,
)
from redis import Redis

from core_api.config import get_settings

# One span per command; the instrumentation replaces every argument with "?".
_instrumentor = RedisInstrumentor()
if not _instrumentor.is_instrumented_by_opentelemetry:
    _instrumentor.instrument()  # pyright: ignore[reportUnknownMemberType]  # untyped kwargs


def redis_from_url(url: str, timeout: float = 1.0) -> Redis:
    """The one place that builds a client: redis-py leaves `from_url`'s kwargs untyped."""
    return Redis.from_url(  # pyright: ignore[reportUnknownMemberType]
        url, socket_timeout=timeout, socket_connect_timeout=timeout
    )


@lru_cache
def get_redis() -> Redis:
    # Short timeouts: a hung Redis must fail the request quickly (rate limits fail closed).
    return redis_from_url(get_settings().redis_url.get_secret_value())
