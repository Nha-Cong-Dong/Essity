"""The Redis connection of ai-service: the event consumer reads `events.core` through it (T4.3).

Not instrumented with OpenTelemetry, unlike core-api's: the consumer blocks on XREADGROUP every
second, and a span per poll would bury the spans that matter. The consumer opens its own span
per event instead.
"""

from redis import Redis

# Short enough that a hung Redis fails a round quickly, and longer than the consumer's block
# (BLOCK_MS): the socket must not time out while XREADGROUP is legitimately waiting.
SOCKET_TIMEOUT_S = 5.0


def redis_from_url(url: str, timeout: float = SOCKET_TIMEOUT_S) -> Redis:
    """The one place that builds a client: redis-py leaves `from_url`'s kwargs untyped.

    Responses are decoded: stream fields are JSON text and ids are ASCII. Bytes that are not
    UTF-8 become U+FFFD instead of raising: one bad entry must not stop every XAUTOCLAIM
    (review 🟡A); the text then fails the contract and goes to the dead letter.
    """
    return Redis.from_url(  # pyright: ignore[reportUnknownMemberType]
        url,
        decode_responses=True,
        encoding_errors="replace",
        socket_timeout=timeout,
        socket_connect_timeout=timeout,
    )
