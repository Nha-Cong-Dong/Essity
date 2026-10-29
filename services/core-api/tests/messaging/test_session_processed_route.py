"""T4.17: the consumer routes `session.processed.v1` to its handler (it was `no_handler`)."""

import json
import uuid
from collections.abc import Callable
from typing import Any

from redis import Redis

from core_api.handlers.session_processed import OnSessionProcessed
from core_api.messaging.consumer import Consumer, build_handlers
from fake_storage import FakeStorage
from messaging.test_consumer import dead_letters, publish
from messaging.test_consumer import make_consumer as make_consumer  # noqa: F401
from messaging.test_consumer import streams as streams  # noqa: F401


def test_build_handlers_handles_session_processed() -> None:
    assert isinstance(build_handlers()["session.processed.v1"], OnSessionProcessed)


def test_consumer_routes_session_processed(
    make_consumer: Callable[..., Consumer],  # noqa: F811
    redis_client: Redis,
    streams: tuple[str, str],  # noqa: F811
) -> None:
    # Red when: the event type has no handler (dead letter "no_handler").
    source, dead = streams
    user, session_id = uuid.uuid4(), uuid.uuid4()
    envelope: dict[str, Any] = {
        "event_id": str(uuid.uuid4()),
        "event_type": "session.processed.v1",
        "schema_version": 1,
        "occurred_at": "2026-10-29T08:01:00.000000Z",
        "user_id": str(user),
        "trace_context": {},
        "payload": {
            "study_session_id": str(session_id),
            "run_id": str(uuid.uuid4()),
            "result_key": f"users/{user}/subjects/{uuid.uuid4()}/sessions/{session_id}/"
            f"result-{uuid.uuid4()}.json",
        },
    }
    publish(redis_client, source, json.dumps(envelope))
    consumer = make_consumer({"session.processed.v1": OnSessionProcessed(FakeStorage())})
    assert consumer.consume_once() == ["processed"]  # no such session for that user: ignored
    assert dead_letters(redis_client, dead) == []
