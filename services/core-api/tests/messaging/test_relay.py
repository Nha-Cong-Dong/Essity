"""T4.2 (ADR-0006): the relay reads the outbox and writes each event to a Redis stream, at least
once. Real PostgreSQL and Redis; every test writes to a stream of its own (`stream` fixture)."""

import json
import signal
import threading
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pytest
import sqlalchemy
from redis import Redis
from sqlalchemy import Engine, update
from sqlalchemy.orm import Session

from core_api.clients.redis import redis_from_url
from core_api.db.models import Outbox
from core_api.messaging.envelope import DocumentUploaded, UserDeleted
from core_api.messaging.outbox import CorePayload, enqueue_event
from core_api.messaging.relay import (
    MAX_DELAY,
    install_signal_handlers,
    relay_once,
    retry_delay,
    run,
)
from races import SECONDS_TO_WAIT, finished, in_thread
from test_event_contracts import validator

pytestmark = pytest.mark.usefixtures("clean_outbox")

NOW = datetime(2026, 10, 25, 8, 30, tzinfo=UTC)
Entries = list[tuple[bytes, dict[bytes, bytes]]]


def enqueue(engine: Engine, payload: CorePayload | None = None, **kwargs: Any) -> uuid.UUID:
    user_id = kwargs.pop("user_id", uuid.uuid4())
    with Session(engine) as session:
        event_id = enqueue_event(session, payload or UserDeleted(), user_id=user_id, now=NOW)
        session.commit()
    return event_id


def saved(engine: Engine, event_id: uuid.UUID) -> Outbox:
    with Session(engine) as session:
        row = session.get(Outbox, event_id)
        assert row is not None
        return row


def entries(redis: Redis, stream: str) -> Entries:
    return cast(Entries, redis.xrange(stream))


def envelopes(redis: Redis, stream: str) -> list[dict[str, Any]]:
    return [json.loads(fields[b"envelope"]) for _, fields in entries(redis, stream)]


def test_relay_sends_due_rows_and_marks_them_sent(
    engine: Engine, redis_client: Redis, stream: str
) -> None:
    # Red when: the relay sends nothing, or leaves sent rows unmarked so they go out forever.
    ids = [enqueue(engine), enqueue(engine)]
    assert relay_once(engine, redis_client, now=NOW, stream=stream) == 2
    assert [e["event_id"] for e in envelopes(redis_client, stream)] == [str(i) for i in ids]
    assert all(saved(engine, i).sent_at == NOW for i in ids)
    assert relay_once(engine, redis_client, now=NOW, stream=stream) == 0
    assert len(entries(redis_client, stream)) == 2


def test_wire_format_is_one_envelope_field_that_matches_the_schema(
    engine: Engine, redis_client: Redis, stream: str
) -> None:
    # Red when: the stream entry drifts from contracts/events/README.md (one field `envelope`,
    # the event as JSON) or from the schema ai-service validates against (plan Y3).
    user_id = uuid.uuid4()
    payload = DocumentUploaded(
        document_id=uuid.uuid4(),
        subject_id=uuid.uuid4(),
        object_key=f"users/{user_id}/subjects/{uuid.uuid4()}/raw/a.pdf",
    )
    enqueue(engine, payload, user_id=user_id)
    relay_once(engine, redis_client, now=NOW, stream=stream)
    [(_, fields)] = entries(redis_client, stream)
    assert list(fields) == [b"envelope"]
    envelope = json.loads(fields[b"envelope"])
    validator("envelope").validate(envelope)
    validator("document.uploaded.v1").validate(envelope)
    assert envelope["payload"] == payload.model_dump(mode="json")
    assert envelope["occurred_at"] == "2026-10-25T08:30:00Z"


def test_event_user_id_matches_column(engine: Engine, redis_client: Redis, stream: str) -> None:
    # Red when: the envelope's user_id comes from anywhere but the row's column, which T6.3
    # deletes by (plan E2).
    user_id = uuid.uuid4()
    event_id = enqueue(engine, user_id=user_id)
    relay_once(engine, redis_client, now=NOW, stream=stream)
    [envelope] = envelopes(redis_client, stream)
    assert envelope["user_id"] == str(user_id) == str(saved(engine, event_id).user_id)


def test_rows_not_yet_due_wait(engine: Engine, redis_client: Redis, stream: str) -> None:
    # Red when: the relay ignores available_at, so backoff never holds a row back.
    event_id = enqueue(engine)
    assert relay_once(engine, redis_client, now=NOW - timedelta(seconds=1), stream=stream) == 0
    assert saved(engine, event_id).sent_at is None


def test_oldest_rows_go_first_in_batches(engine: Engine, redis_client: Redis, stream: str) -> None:
    # Red when: a batch is not the oldest rows by seq, or the batch size is not respected.
    ids = [enqueue(engine) for _ in range(3)]
    # Neither the table's physical order nor the index's (available_at, seq) is seq order now:
    # the first row is rewritten (its new version sits last), the others came due earlier.
    with Session(engine) as session:
        session.execute(update(Outbox).where(Outbox.id == ids[0]).values(available_at=NOW))
        earlier = NOW - timedelta(minutes=1)
        session.execute(update(Outbox).where(Outbox.id != ids[0]).values(available_at=earlier))
        session.commit()
    assert relay_once(engine, redis_client, now=NOW, stream=stream, batch=2) == 2
    assert [e["event_id"] for e in envelopes(redis_client, stream)] == [str(i) for i in ids[:2]]
    assert relay_once(engine, redis_client, now=NOW, stream=stream, batch=2) == 1


# --- At least once: a crash after XADD sends again ------------------------------------------


class Crash(Exception):
    """The relay process dying after Redis took the events, before the commit."""


class _CrashingPipeline:
    def __init__(self, real: Any) -> None:
        self._real = real

    def xadd(self, *args: Any, **kwargs: Any) -> Any:
        return self._real.xadd(*args, **kwargs)

    def execute(self) -> list[Any]:
        self._real.execute()
        raise Crash


class CrashingRedis:
    def __init__(self, real: Redis) -> None:
        self._real = real

    def pipeline(self, transaction: bool = True) -> _CrashingPipeline:
        real = self._real.pipeline(transaction=transaction)  # pyright: ignore[reportUnknownMemberType]
        return _CrashingPipeline(real)


def test_relay_crash_between_xadd_and_commit_resends(
    engine: Engine, redis_client: Redis, stream: str
) -> None:
    # Red when: a row is marked sent before Redis has the event (an event could be lost), or the
    # mark survives a crash before the commit (T4.2 "Xong khi": sent again, consumers dedupe).
    event_id = enqueue(engine)
    with pytest.raises(Crash):
        relay_once(engine, cast(Redis, CrashingRedis(redis_client)), now=NOW, stream=stream)
    assert saved(engine, event_id).sent_at is None
    assert relay_once(engine, redis_client, now=NOW, stream=stream) == 1
    assert [e["event_id"] for e in envelopes(redis_client, stream)] == [str(event_id)] * 2
    assert saved(engine, event_id).sent_at == NOW


# --- Two relays at once --------------------------------------------------------------------


class _BlockingPipeline:
    def __init__(self, real: Any, inside: threading.Event, release: threading.Event) -> None:
        self._real, self._inside, self._release = real, inside, release

    def xadd(self, *args: Any, **kwargs: Any) -> Any:
        return self._real.xadd(*args, **kwargs)

    def execute(self) -> list[Any]:
        self._inside.set()
        assert self._release.wait(SECONDS_TO_WAIT * 3)
        return self._real.execute()


class BlockingRedis:
    """Stops inside XADD until released, while the relay holds its row locks."""

    def __init__(self, real: Redis) -> None:
        self._real = real
        self.inside, self.release = threading.Event(), threading.Event()

    def pipeline(self, transaction: bool = True) -> _BlockingPipeline:
        real = self._real.pipeline(transaction=transaction)  # pyright: ignore[reportUnknownMemberType]
        return _BlockingPipeline(real, self.inside, self.release)


def test_two_relays_no_duplicate_xadd(
    engine: Engine, redis_client: Redis, stream: str, test_database_url: str
) -> None:
    # Red when: a second relay reads rows the first is sending (no FOR UPDATE: sent twice), or
    # waits for them (no SKIP LOCKED: two relays take turns instead of sharing the work).
    enqueue(engine)
    blocking = BlockingRedis(redis_client)
    thread, outcome = in_thread(
        lambda: relay_once(engine, cast(Redis, blocking), now=NOW, stream=stream)
    )
    try:
        assert blocking.inside.wait(SECONDS_TO_WAIT), "relay A never reached XADD"
        # Relay B, on its own connection; a lock wait fails fast instead of hanging the test.
        other = sqlalchemy.create_engine(
            test_database_url, connect_args={"options": "-c lock_timeout=500"}
        )
        try:
            assert relay_once(other, redis_client, now=NOW, stream=stream) == 0
        finally:
            other.dispose()
    finally:
        blocking.release.set()
    assert finished(thread, outcome) == 1
    assert len(entries(redis_client, stream)) == 1


# --- Redis down ----------------------------------------------------------------------------


# The class name a dead Redis gives: refused on Linux, a connect timeout on Windows.
REDIS_DOWN = {"ConnectionError", "TimeoutError"}


@pytest.fixture
def dead_redis() -> Redis:
    """A client to a port nothing listens on: every command fails."""
    return redis_from_url("redis://127.0.0.1:9/0", timeout=0.2)


def test_a_row_the_contract_refuses_waits_without_blocking_the_rest(
    engine: Engine, redis_client: Redis, stream: str
) -> None:
    # Red when: one row that no longer validates (edited by hand, say) fails every batch it is in,
    # so no event behind it is ever sent; or it is sent anyway, or dropped.
    bad, good = enqueue(engine), enqueue(engine)
    with Session(engine) as session:
        session.execute(update(Outbox).where(Outbox.id == bad).values(payload={"extra": 1}))
        session.commit()
    assert relay_once(engine, redis_client, now=NOW, stream=stream) == 1
    assert [e["event_id"] for e in envelopes(redis_client, stream)] == [str(good)]
    row = saved(engine, bad)
    assert (row.sent_at, row.attempts, row.last_error) == (None, 1, "ValidationError")
    assert row.available_at == NOW + retry_delay(1)


def test_redis_down_keeps_row_unsent_and_backs_off(
    engine: Engine, redis_client: Redis, dead_redis: Redis, stream: str
) -> None:
    # Red when: a failed send drops the row, marks it sent, or retries it at once forever
    # (plan fix 3: never drop, delay min(2**attempts, 30) s).
    event_id = enqueue(engine)
    assert relay_once(engine, dead_redis, now=NOW, stream=stream) == 0
    row = saved(engine, event_id)
    assert (row.sent_at, row.attempts) == (None, 1)
    assert row.last_error in REDIS_DOWN
    assert NOW < row.available_at <= NOW + timedelta(seconds=30)
    # Redis is back, but the row waits its turn; then it goes.
    assert relay_once(engine, redis_client, now=NOW, stream=stream) == 0
    assert relay_once(engine, redis_client, now=NOW + timedelta(seconds=31), stream=stream) == 1
    assert saved(engine, event_id).sent_at == NOW + timedelta(seconds=31)


def test_backoff_is_capped_after_many_attempts(
    engine: Engine, dead_redis: Redis, stream: str
) -> None:
    # Red when: the delay grows without bound, so a long Redis outage leaves events days late.
    event_id = enqueue(engine)
    with Session(engine) as session:
        session.execute(update(Outbox).where(Outbox.id == event_id).values(attempts=1000))
        session.commit()
    relay_once(engine, dead_redis, now=NOW, stream=stream)
    row = saved(engine, event_id)
    assert (row.attempts, row.available_at) == (1001, NOW + MAX_DELAY)


@pytest.mark.parametrize(
    ("attempts", "seconds"), [(1, 2), (2, 4), (4, 16), (5, 30), (6, 30), (10**6, 30)]
)
def test_retry_delay(attempts: int, seconds: int) -> None:
    # Red when: the backoff formula changes from min(2**attempts, 30) s.
    assert retry_delay(attempts) == timedelta(seconds=seconds)


# --- Logs and lifecycle --------------------------------------------------------------------


def test_relay_logs_no_payload(
    engine: Engine,
    redis_client: Redis,
    dead_redis: Redis,
    stream: str,
    log_output: Callable[[], str],
) -> None:
    # Red when: a relay log line carries an object key, a user id or any of the payload
    # (ADR-0013: logs hold counts and class names).
    user_id = uuid.uuid4()
    key = f"users/{user_id}/subjects/{uuid.uuid4()}/raw/secret-name.pdf"
    payload = DocumentUploaded(document_id=uuid.uuid4(), subject_id=uuid.uuid4(), object_key=key)
    enqueue(engine, payload, user_id=user_id)
    relay_once(engine, dead_redis, now=NOW, stream=stream)
    relay_once(engine, redis_client, now=NOW + MAX_DELAY, stream=stream)
    lines = [json.loads(line) for line in log_output().splitlines()]
    relay_lines = [line for line in lines if line["logger"] == "core_api.messaging"]
    assert [line["message"] for line in relay_lines] == ["outbox send failed", "outbox relayed"]
    assert relay_lines[0]["error_type"] in REDIS_DOWN
    assert relay_lines[1]["event_count"] == 1
    text = log_output()
    for secret in (key, "secret-name", str(user_id), str(payload.document_id)):
        assert secret not in text


def test_run_stops_when_asked(engine: Engine, redis_client: Redis, stream: str) -> None:
    # Red when: the loop ignores the stop signal, so SIGTERM waits for Compose to kill it.
    stop = threading.Event()
    thread, outcome = in_thread(lambda: run(engine, redis_client, stop, stream=stream))
    enqueue(engine)
    stop.set()
    assert finished(thread, outcome) is None


def test_sigterm_sets_the_stop_event() -> None:
    # Red when: SIGTERM (docker stop) does not reach the loop.
    stop = threading.Event()
    saved_handlers = {sig: signal.getsignal(sig) for sig in (signal.SIGTERM, signal.SIGINT)}
    try:
        install_signal_handlers(stop)
        signal.raise_signal(signal.SIGTERM)
        assert stop.is_set()
    finally:
        for sig, handler in saved_handlers.items():
            signal.signal(sig, handler)
