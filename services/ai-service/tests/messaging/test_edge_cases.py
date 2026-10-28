"""T4.3: edge cases found by the independent tester's mutation run.

Each test names the change in `src/` that turns it red.
"""

import uuid
from types import SimpleNamespace
from typing import Any, cast

import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from pydantic import BaseModel
from redis import Redis
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.orm import Session, sessionmaker

from ai_service.logging import user_id_var
from ai_service.messaging.consumer import is_outage, keys_belong_to_user
from ai_service.messaging.dead_letter import purge_user, replay, send_to_dead
from ai_service.messaging.envelope import Event, ObjectKey
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


class _Inner(BaseModel):
    key: ObjectKey


class _Outer(BaseModel):
    maybe_key: ObjectKey | None  # typing.Union: Annotated is not a class
    maybe_keys: list[ObjectKey] | None  # types.UnionType
    inner: _Inner
    inner_list: list[_Inner]


FIELDS = ("maybe_key", "maybe_keys", "inner", "inner_list")


def _owned_by(user: uuid.UUID, payload: BaseModel) -> bool:
    # Only `user_id` and `payload` are read: a payload shape no contract event has yet.
    return keys_belong_to_user(cast(Event, SimpleNamespace(user_id=user, payload=payload)))


def _key(owner: uuid.UUID) -> str:
    return f"users/{owner}/subjects/s/raw/a.pdf"


@pytest.mark.parametrize("moved", FIELDS)
def test_t43_object_key_check_reaches_optionals_and_nested_models(moved: str) -> None:
    # Review 🟡8 / D6: the check goes by type through `X | None` and nested models, not only
    # through the shapes today's contract examples use (none has an optional key or a key in a
    # nested model). Red when: `_object_keys` stops following `Union`/`UnionType` or a nested
    # model's fields, and a new event with such a key lets user A point at user B's file.
    user, other = uuid.uuid4(), uuid.uuid4()
    owners = {name: other if name == moved else user for name in FIELDS}
    payload = _Outer(
        maybe_key=_key(owners["maybe_key"]),
        maybe_keys=[_key(user), _key(owners["maybe_keys"])],
        inner=_Inner(key=_key(owners["inner"])),
        inner_list=[_Inner(key=_key(user)), _Inner(key=_key(owners["inner_list"]))],
    )
    assert _owned_by(user, payload) is False
    mine = _Outer(maybe_key=None, maybe_keys=None, inner=_Inner(key=_key(user)), inner_list=[])
    assert _owned_by(user, mine) is True


def test_t43_dead_letter_copy_and_ack_go_in_one_transaction(redis_client: Redis) -> None:
    # Plan "dead letter MULTI". Red when: `send_to_dead` sends XADD and XACK without MULTI/EXEC;
    # a consumer killed between the two leaves the entry both dead and pending, and it is dead
    # lettered a second time. Redis gives no way to kill a client between two commands in a
    # test, so this watches the pipeline it opens.
    seen: list[tuple[bool, list[str]]] = []
    real = cast(Any, redis_client.pipeline)  # pyright: ignore[reportUnknownMemberType]

    def spy(transaction: bool = True, shard_hint: Any = None) -> Any:
        pipe: Any = real(transaction=transaction, shard_hint=shard_hint)
        execute = pipe.execute

        def watched(raise_on_error: bool = True) -> Any:
            stack = cast(list[tuple[tuple[Any, ...], Any]], pipe.command_stack)
            seen.append((transaction, [str(args[0]) for args, _ in stack]))
            return execute(raise_on_error)

        pipe.execute = watched
        return pipe

    tag = uuid.uuid4()
    dead = f"test.events.dead.{tag}"
    redis_client.pipeline = spy  # pyright: ignore[reportAttributeAccessIssue]
    try:
        send_to_dead(
            redis_client,
            dead_stream=dead,
            stream=f"test.events.core.{tag}",
            group="g",
            entry_id="1-0",
            envelope="",
            reason="invalid_envelope",
            deliveries=1,
        )
    finally:
        del redis_client.pipeline  # pyright: ignore[reportAttributeAccessIssue]
        redis_client.delete(dead)
    assert seen == [(True, ["XADD", "XACK"])]
