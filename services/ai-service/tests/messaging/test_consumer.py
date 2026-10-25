"""T4.3: the consumer of `events.core`, on a real Redis and the real test PostgreSQL.

PLAN T4.3 "Xong khi": the same event twice runs its handler once; a handler failing past the
limit goes to the dead letter; a deferred task does not (test_deferred.py).
"""

import uuid
from typing import Any

import pytest
from redis import Redis
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy import event as sa_event
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from ai_service.db.models import ProcessedEvent
from ai_service.messaging.consumer import Consumer, Handler
from tests.messaging.conftest import Names
from tests.messaging.helpers import DOCUMENT_UPLOADED, Recorder, boom, publish, uploaded


def make_consumer(
    redis: Redis,
    names: Names,
    session_factory: sessionmaker[Session],
    handlers: dict[str, Handler],
    **overrides: Any,
) -> Consumer:
    options: dict[str, Any] = {
        "redis": redis,
        "session_factory": session_factory,
        "handlers": handlers,
        "stream": names.stream,
        "group": names.group,
        "dead_stream": names.dead,
        "name": "test-consumer",
        "min_idle_ms": 0,  # failed entries come straight back: no waiting in tests
        "block_ms": None,
    }
    return Consumer(**{**options, **overrides})


def pending(redis: Redis, names: Names) -> int:
    return int(redis.xpending(names.stream, names.group)["pending"])  # pyright: ignore[reportUnknownArgumentType, reportUnknownMemberType]


def claimed(session_factory: sessionmaker[Session], group: str, event_id: str) -> bool:
    with session_factory() as session:
        row = session.scalar(
            select(ProcessedEvent).where(
                ProcessedEvent.consumer == group, ProcessedEvent.event_id == uuid.UUID(event_id)
            )
        )
        return row is not None


def test_t43_event_published_before_group_creation_is_received(
    redis_client: Redis, names: Names, session_factory: sessionmaker[Session]
) -> None:
    # Plan Y1: the group starts at 0, not $, so events relayed before ai-service ever ran count.
    event = uploaded()
    publish(redis_client, names.stream, event)
    recorder = Recorder()
    consumer = make_consumer(redis_client, names, session_factory, {DOCUMENT_UPLOADED: recorder})
    consumer.ensure_group()
    consumer.ensure_group()  # BUSYGROUP is fine: a restart finds the group there
    assert consumer.run_once() == ["processed"]
    assert [str(e.event_id) for e in recorder.calls] == [event["event_id"]]
    assert pending(redis_client, names) == 0
    assert claimed(session_factory, names.group, event["event_id"])


def test_t43_same_event_twice_handler_runs_once(
    redis_client: Redis, names: Names, session_factory: sessionmaker[Session]
) -> None:
    # Xong khi 1. Red when: the claim is skipped, and a relay resend runs the work twice.
    event = uploaded()
    publish(redis_client, names.stream, event)
    publish(redis_client, names.stream, event)
    recorder = Recorder()
    consumer = make_consumer(redis_client, names, session_factory, {DOCUMENT_UPLOADED: recorder})
    consumer.ensure_group()
    assert consumer.run_once() == ["processed", "duplicate"]
    assert len(recorder.calls) == 1
    assert pending(redis_client, names) == 0  # the duplicate is acknowledged too


def test_t43_handler_error_not_acked_then_redelivered(
    redis_client: Redis, names: Names, session_factory: sessionmaker[Session]
) -> None:
    # Red when: the entry is acknowledged before the handler succeeds, and a failure loses it.
    event = uploaded()
    publish(redis_client, names.stream, event)
    recorder = Recorder(fail_with=boom)
    consumer = make_consumer(redis_client, names, session_factory, {DOCUMENT_UPLOADED: recorder})
    consumer.ensure_group()
    assert consumer.run_once() == ["retry"]
    assert pending(redis_client, names) == 1
    assert not claimed(session_factory, names.group, event["event_id"])
    recorder.fail_with = None
    assert consumer.run_once() == ["processed"]
    assert len(recorder.calls) == 2
    assert pending(redis_client, names) == 0


def test_t43_commit_failure_after_handler_rolls_back_claim(
    redis_client: Redis, names: Names, session_factory: sessionmaker[Session]
) -> None:
    # Red when: the entry is acknowledged before COMMIT, and a failed commit loses the event.
    event = uploaded()
    publish(redis_client, names.stream, event)

    def failing_sessions() -> Session:
        session = session_factory()

        def refuse(session: Session) -> None:
            raise boom()

        sa_event.listen(session, "before_commit", refuse)
        return session

    recorder = Recorder()
    consumer = make_consumer(redis_client, names, session_factory, {DOCUMENT_UPLOADED: recorder})
    consumer.session_factory = failing_sessions
    consumer.ensure_group()
    assert consumer.run_once() == ["retry"]
    assert len(recorder.calls) == 1
    assert pending(redis_client, names) == 1
    assert not claimed(session_factory, names.group, event["event_id"])


class AckFailsOnce(Redis):
    """Redis whose first XACK fails as if the connection dropped right after the commit."""

    failed = False

    def xack(self, name: Any, groupname: Any, *ids: Any) -> Any:
        if not self.failed:
            self.failed = True
            raise RedisConnectionError("connection lost")
        return super().xack(name, groupname, *ids)


def test_t43_crash_between_commit_and_ack_redelivery_is_skipped(
    redis_client: Redis, names: Names, session_factory: sessionmaker[Session]
) -> None:
    # Red when: the claim is not committed with the handler, and the redelivery runs it again.
    event = uploaded()
    publish(redis_client, names.stream, event)
    flaky = AckFailsOnce(connection_pool=redis_client.connection_pool)
    recorder = Recorder()
    consumer = make_consumer(flaky, names, session_factory, {DOCUMENT_UPLOADED: recorder})
    consumer.ensure_group()
    with pytest.raises(RedisConnectionError):
        consumer.run_once()
    assert claimed(session_factory, names.group, event["event_id"])
    assert consumer.run_once() == ["duplicate"]
    assert len(recorder.calls) == 1
    assert pending(redis_client, names) == 0


def test_t43_xautoclaim_picks_up_pending_entry_of_dead_consumer(
    redis_client: Redis, names: Names, session_factory: sessionmaker[Session]
) -> None:
    # Red when: only new entries are read, and an entry a crashed consumer held is never done.
    event = uploaded()
    publish(redis_client, names.stream, event)
    recorder = Recorder()
    consumer = make_consumer(redis_client, names, session_factory, {DOCUMENT_UPLOADED: recorder})
    consumer.ensure_group()
    redis_client.xreadgroup(names.group, "crashed-consumer", {names.stream: ">"}, count=1)
    assert consumer.run_once() == ["processed"]
    assert len(recorder.calls) == 1
    assert pending(redis_client, names) == 0


def test_t43_trimmed_pending_entry_never_reaches_handler(
    redis_client: Redis, names: Names, session_factory: sessionmaker[Session]
) -> None:
    # Review 🟡3: an entry trimmed (MAXLEN) while pending is dropped from the PEL by XAUTOCLAIM.
    entry_id = publish(redis_client, names.stream, uploaded())
    recorder = Recorder()
    consumer = make_consumer(redis_client, names, session_factory, {DOCUMENT_UPLOADED: recorder})
    consumer.ensure_group()
    redis_client.xreadgroup(names.group, "crashed-consumer", {names.stream: ">"}, count=1)
    redis_client.xdel(names.stream, entry_id)
    assert consumer.run_once() == []
    assert recorder.calls == []
    assert pending(redis_client, names) == 0
