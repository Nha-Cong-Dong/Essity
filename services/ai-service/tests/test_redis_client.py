"""T4.3: the one place ai-service builds a Redis client."""

from redis import Redis

from ai_service.clients.redis import redis_from_url


def test_t43_client_answers_and_decodes_text(redis_client: Redis) -> None:
    # Red when: decode_responses is off, and every stream field comes back as bytes.
    key = "test.t43.client"
    redis_client.set(key, "x", ex=5)
    assert redis_client.get(key) == "x"


def test_t43_client_has_short_timeouts() -> None:
    # Red when: no socket timeout, and a hung Redis stalls the consumer for ever.
    client = redis_from_url("redis://127.0.0.1:9/0")
    kwargs = client.connection_pool.connection_kwargs
    assert kwargs["socket_connect_timeout"] is not None
    assert kwargs["socket_timeout"] is not None
