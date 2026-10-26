"""T4.3: edge cases found by the independent tester's mutation run.

Each test names the change in `src/` that turns it red.
"""

import uuid
from typing import Any

import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from redis import Redis
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.orm import Session, sessionmaker

from ai_service.logging import user_id_var
from ai_service.messaging.consumer import is_outage
from ai_service.messaging.dead_letter import purge_user, replay
from tests.messaging.conftest import Names
from tests.messaging.helpers import (
    DOCUMENT_UPLOADED,
    SECRET_DETAIL,
    Recorder,
    publish,
    uploaded,
)
from tests.messaging.test_consumer import make_consumer, pending
from tests.messaging.test_deferred import times_delivered
from tests.messaging.test_failures import dead_entries

SPAN_NAME = "events.core process"


def test_t43_user_id_context_is_restored_after_a_valid_entry(
    redis_client: Redis, names: Names, session_factory: sessionmaker[Session]
) -> None:
    # Red when: `user_id_var.reset(...)` is dropped from `handle`. The last entry of a round is
    # a valid event, so the user stays in the loop's context and the next "round failed" line
    # (or the next process step) is written under their name.
    publish(redis_client, names.stream, uploaded())
    consumer = make_consumer(redis_client, names, session_factory, {DOCUMENT_UPLOADED: Recorder()})
    consumer.ensure_group()
    token = user_id_var.set("outer")
    try:
        assert consumer.run_once() == ["processed"]
        assert user_id_var.get() == "outer"
    finally:
        user_id_var.reset(token)


class AckFailsWithDetail(Redis):
    """Redis whose XACK fails with a message that must not reach a span."""

    def xack(self, name: Any, groupname: Any, *ids: Any) -> Any:
        raise RedisConnectionError(SECRET_DETAIL)


def test_t43_exception_escaping_the_entry_is_not_recorded_on_the_span(
    redis_client: Redis,
    names: Names,
    session_factory: sessionmaker[Session],
    spans: InMemorySpanExporter,
) -> None:
    # ADR-0013. Red when: the consumer span is opened with `record_exception=True` (or
    # `set_status_on_exception=True` with its description): an error raised out of the entry
    # (here the XACK after COMMIT) would put its message on the span as an "exception" event.
    publish(redis_client, names.stream, uploaded())
    flaky = AckFailsWithDetail(connection_pool=redis_client.connection_pool)
    consumer = make_consumer(flaky, names, session_factory, {DOCUMENT_UPLOADED: Recorder()})
    consumer.ensure_group()
    with pytest.raises(RedisConnectionError):
        consumer.run_once()
    [span] = [s for s in spans.get_finished_spans() if s.name == SPAN_NAME]
    assert not span.events
    assert span.status.description is None
    assert SECRET_DETAIL not in repr(dict(span.attributes or {}))


def invalidated() -> Exception:
    # Not an OperationalError: only `connection_invalidated` says the connection is gone.
    return DBAPIError("SELECT 1", {}, Exception("x"), connection_invalidated=True)


def test_t43_invalidated_connection_is_an_outage() -> None:
    # Red when: the `connection_invalidated` branch of `is_outage` is dropped.
    assert is_outage(invalidated()) is True
    assert is_outage(DBAPIError("SELECT 1", {}, Exception("x"))) is False


def test_t43_invalidated_connection_does_not_burn_attempts(
    redis_client: Redis, names: Names, session_factory: sessionmaker[Session]
) -> None:
    # Review 🟠1. Red when: an error SQLAlchemy flagged as a lost connection counts as a
    # delivery, and a database restart sends events to the dead letter.
    publish(redis_client, names.stream, uploaded())
    recorder = Recorder(fail_with=invalidated)
    consumer = make_consumer(redis_client, names, session_factory, {DOCUMENT_UPLOADED: recorder})
    consumer.ensure_group()
    for _ in range(6):
        assert consumer.run_once() == ["unavailable"]
    assert times_delivered(redis_client, names) <= 1
    assert dead_entries(redis_client, names) == []


def test_t43_outage_while_checking_an_overdelivered_entry_puts_it_back(
    redis_client: Redis, names: Names, session_factory: sessionmaker[Session]
) -> None:
    # Review 🟡4 + 🟠1. Red when: an outage in the `was_processed` check of an entry delivered
    # more than `max_attempts` times sends it to the dead letter (or raises), although the
    # database is only down and the event may well have been handled already.
    entry_id = publish(redis_client, names.stream, uploaded())
    consumer = make_consumer(redis_client, names, session_factory, {DOCUMENT_UPLOADED: Recorder()})
    consumer.ensure_group()
    redis_client.xreadgroup(names.group, "crashed-consumer", {names.stream: ">"}, count=1)
    redis_client.xclaim(names.stream, names.group, "crashed-consumer", 0, [entry_id], retrycount=5)

    def down() -> Session:
        raise OperationalError("SELECT 1", {}, Exception("server closed the connection"))

    consumer.session_factory = down
    assert consumer.run_once() == ["unavailable"]
    assert dead_entries(redis_client, names) == []
    assert pending(redis_client, names) == 1
    # Put back as it was before this delivery: still past the limit, checked again next time.
    assert times_delivered(redis_client, names) == 5


def test_t43_purge_and_replay_on_an_empty_dead_letter(redis_client: Redis, names: Names) -> None:
    # Empty input. Red when: purge calls XDEL with no ids (a Redis error), or replay fails on a
    # dead stream that does not exist yet.
    assert purge_user(redis_client, dead_stream=names.dead, user_id=uuid.uuid4()) == 0
    assert replay(redis_client, dead_stream=names.dead, stream=names.stream) == 0
    assert replay(redis_client, dead_stream=names.dead, stream=names.stream, ids=["1-0"]) == 0
