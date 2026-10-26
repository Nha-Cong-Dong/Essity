"""T4.4 (ADR-0006): core-api reads ai → core events from a Redis stream in a consumer group,
handles each once, retries a failing handler by redelivery and moves what cannot be handled to
the dead letter stream. Real PostgreSQL and Redis; every test has streams of its own."""

import json
import signal
import threading
import uuid
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import psycopg
import psycopg.errors
import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind
from redis import Redis
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError
from sqlalchemy import Engine
from sqlalchemy.exc import DBAPIError, OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from core_api.db.models import Outbox, ProcessedEvent
from core_api.logging import user_id_var
from core_api.messaging.consumer import (
    MAX_DELIVERIES,
    SPAN_NAME,
    Consumer,
    Handler,
    backoff_ms,
    install_signal_handlers,
    is_outage,
    keys_belong_to_user,
    pause_s,
    run,
)
from core_api.messaging.envelope import (
    Event,
    SessionProcessed,
    SessionProcessedEvent,
    SessionProgress,
    SessionProgressEvent,
    TraceContext,
    dump_event,
    parse_event,
)
from core_api.messaging.idempotency import claim
from races import finished, in_thread

NOW = datetime(2026, 10, 26, 8, 30, tzinfo=UTC)
TRACEPARENT = "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"
Entries = list[tuple[bytes, dict[bytes, bytes]]]


class Boom(Exception):
    """A handler failing."""


@pytest.fixture
def streams(stream: str) -> tuple[str, str]:
    """The test's own events stream and dead letter stream."""
    return stream, f"{stream}.dead"


@pytest.fixture
def make_consumer(
    engine: Engine, redis_client: Redis, streams: tuple[str, str]
) -> Iterator[Callable[..., Consumer]]:
    def make(handlers: dict[str, Handler], **kwargs: Any) -> Consumer:
        source, dead = streams
        consumer = Consumer(
            engine,
            redis_client,
            handlers,
            stream=source,
            dead_stream=dead,
            name=kwargs.pop("name", "test-consumer"),
            min_idle_ms=kwargs.pop("min_idle_ms", 0),
            block_ms=kwargs.pop("block_ms", None),
            clock=lambda: NOW,
            **kwargs,
        )
        consumer.ensure_group()
        return consumer

    yield make
    redis_client.delete(*streams)


def progress_event(**overrides: Any) -> SessionProgressEvent:
    fields: dict[str, Any] = {
        "event_id": uuid.uuid4(),
        "event_type": "session.progress.v1",
        "schema_version": 1,
        "occurred_at": NOW,
        "user_id": uuid.uuid4(),
        "trace_context": {},
        "payload": SessionProgress(
            study_session_id=uuid.uuid4(), run_id=uuid.uuid4(), step="anchoring", percent=40
        ),
    }
    fields.update(overrides)
    return SessionProgressEvent.model_validate(fields)


def publish(redis: Redis, stream: str, envelope: str | bytes) -> bytes:
    return cast(bytes, redis.xadd(stream, {"envelope": envelope}))


def pending(redis: Redis, stream: str, group: str = "core-api") -> int:
    return redis.xpending(stream, group)["pending"]


def dead_letters(redis: Redis, stream: str) -> list[dict[bytes, bytes]]:
    return [fields for _, fields in cast(Entries, redis.xrange(stream))]


class Recorder:
    """A handler that records the events it saw and fails while `failures` is above zero."""

    def __init__(self, failures: int = 0) -> None:
        self.seen: list[Event] = []
        self.failures = failures

    def __call__(self, session: Session, event: Event) -> None:
        self.seen.append(event)
        if self.failures:
            self.failures -= 1
            raise Boom


def processed(engine: Engine, event_id: uuid.UUID) -> bool:
    with Session(engine) as session:
        return session.get(ProcessedEvent, ("core-api", event_id)) is not None


# --- Once ----------------------------------------------------------------------------------


def test_same_event_twice_handler_runs_once(
    make_consumer: Callable[..., Consumer], redis_client: Redis, streams: tuple[str, str]
) -> None:
    # Red when: the consumer does not claim the event before its handler, so a redelivery (the
    # relay resends after a crash) runs the handler again (T4.4 "Xong khi").
    source, _ = streams
    handler = Recorder()
    consumer = make_consumer({"session.progress.v1": handler})
    event = progress_event()
    publish(redis_client, source, dump_event(event))
    publish(redis_client, source, dump_event(event))
    assert consumer.consume_once() == ["processed", "duplicate"]
    assert [seen.event_id for seen in handler.seen] == [event.event_id]
    assert pending(redis_client, source) == 0


def test_handler_work_and_claim_commit_together(
    engine: Engine,
    make_consumer: Callable[..., Consumer],
    redis_client: Redis,
    streams: tuple[str, str],
) -> None:
    # Red when: the handler's session is not committed, or commits apart from the claim.
    source, _ = streams
    written: list[uuid.UUID] = []

    def handler(session: Session, event: Event) -> None:
        written.append(event.event_id)

    consumer = make_consumer({"session.progress.v1": handler})
    event = progress_event()
    publish(redis_client, source, dump_event(event))
    consumer.consume_once()
    assert written == [event.event_id]
    assert processed(engine, event.event_id)


def test_event_published_before_the_group_exists_is_received(
    make_consumer: Callable[..., Consumer], redis_client: Redis, streams: tuple[str, str]
) -> None:
    # Red when: the group starts at `$` (new entries only), so events ai-service sent while
    # core-api was first starting are never read (plan Y1).
    source, _ = streams
    event = progress_event()
    publish(redis_client, source, dump_event(event))
    handler = Recorder()
    consumer = make_consumer({"session.progress.v1": handler})
    consumer.ensure_group()  # a second start: BUSYGROUP is not an error
    consumer.consume_once()
    assert [seen.event_id for seen in handler.seen] == [event.event_id]


# --- Retry and dead letter -----------------------------------------------------------------


def test_handler_error_not_acked_then_redelivered(
    engine: Engine,
    make_consumer: Callable[..., Consumer],
    redis_client: Redis,
    streams: tuple[str, str],
) -> None:
    # Red when: a failed handler's entry is acknowledged (the event is lost), or its claim is
    # kept (the redelivery skips it).
    source, dead = streams
    handler = Recorder(failures=1)
    consumer = make_consumer({"session.progress.v1": handler})
    event = progress_event()
    publish(redis_client, source, dump_event(event))
    consumer.consume_once()
    assert pending(redis_client, source) == 1
    assert not processed(engine, event.event_id)
    consumer.consume_once()  # min_idle 0: the pending entry is claimed back at once
    assert len(handler.seen) == 2
    assert pending(redis_client, source) == 0
    assert processed(engine, event.event_id)
    assert dead_letters(redis_client, dead) == []


def test_failing_entry_waits_min_idle_before_redelivery(
    make_consumer: Callable[..., Consumer], redis_client: Redis, streams: tuple[str, str]
) -> None:
    # Red when: a failed entry is retried at once, in a tight loop, instead of after min_idle.
    source, _ = streams
    handler = Recorder(failures=1)
    consumer = make_consumer({"session.progress.v1": handler}, min_idle_ms=60_000)
    publish(redis_client, source, dump_event(progress_event()))
    consumer.consume_once()
    consumer.consume_once()
    assert len(handler.seen) == 1
    assert pending(redis_client, source) == 1


def test_handler_fails_over_limit_goes_to_dead_letter(
    make_consumer: Callable[..., Consumer], redis_client: Redis, streams: tuple[str, str]
) -> None:
    # Red when: an event that always fails is retried forever, dropped, or dead-lettered before
    # its MAX_DELIVERIES-th delivery; or the dead letter lacks what is needed to replay it, or
    # carries the exception's message (ADR-0013, plan Y2).
    source, dead = streams
    handler = Recorder(failures=10**6)
    consumer = make_consumer({"session.progress.v1": handler})
    envelope = dump_event(progress_event())
    entry_id = publish(redis_client, source, envelope)
    for _ in range(MAX_DELIVERIES - 1):
        consumer.consume_once()
        assert dead_letters(redis_client, dead) == []
    consumer.consume_once()
    assert len(handler.seen) == MAX_DELIVERIES
    assert pending(redis_client, source) == 0
    assert dead_letters(redis_client, dead) == [
        {
            b"envelope": envelope.encode(),
            b"stream": source.encode(),
            b"entry_id": entry_id,
            b"reason": b"Boom",
            b"deliveries": str(MAX_DELIVERIES).encode(),
        }
    ]
    consumer.consume_once()
    assert len(handler.seen) == MAX_DELIVERIES


def test_entry_delivered_too_often_without_an_error_goes_to_dead_letter(
    make_consumer: Callable[..., Consumer], redis_client: Redis, streams: tuple[str, str]
) -> None:
    # Red when: an entry whose handling kills the process (so no error is ever caught) is
    # redelivered forever.
    source, dead = streams
    handler = Recorder()
    consumer = make_consumer({"session.progress.v1": handler})
    publish(redis_client, source, dump_event(progress_event()))
    # MAX_DELIVERIES deliveries that died with their consumer: read, never acknowledged.
    [[_, [(entry_id, _)]]] = cast(
        list[Any], redis_client.xreadgroup("core-api", "gone", {source: ">"})
    )
    for _ in range(MAX_DELIVERIES - 1):
        redis_client.xclaim(source, "core-api", "gone", 0, [entry_id])
    consumer.consume_once()
    assert handler.seen == []
    [letter] = dead_letters(redis_client, dead)
    assert letter[b"reason"] == b"max_deliveries"
    assert pending(redis_client, source) == 0


@pytest.mark.parametrize(
    "fields",
    [
        {"envelope": "not json"},
        {"envelope": json.dumps({"event_type": "session.progress.v1"})},
        {"something": "else"},
    ],
    ids=["not-json", "not-an-envelope", "no-envelope-field"],
)
def test_poison_envelope_goes_to_dead_letter_without_retry(
    make_consumer: Callable[..., Consumer],
    redis_client: Redis,
    streams: tuple[str, str],
    fields: dict[str, str],
) -> None:
    # Red when: an entry that can never be valid is retried MAX_DELIVERIES times, or crashes the
    # consumer, instead of going to the dead letter at once.
    source, dead = streams
    handler = Recorder()
    consumer = make_consumer({"session.progress.v1": handler})
    redis_client.xadd(source, fields)  # pyright: ignore[reportArgumentType]
    assert consumer.consume_once() == ["dead"]
    assert handler.seen == []
    assert pending(redis_client, source) == 0
    [letter] = dead_letters(redis_client, dead)
    assert (letter[b"reason"], letter[b"deliveries"]) == (b"invalid_envelope", b"1")
    assert letter[b"envelope"] == fields.get("envelope", "").encode()


def test_event_without_a_handler_goes_to_dead_letter(
    make_consumer: Callable[..., Consumer], redis_client: Redis, streams: tuple[str, str]
) -> None:
    # Red when: an event type core-api has no handler for yet is retried, or acknowledged
    # silently. The reason differs from an event type outside the contract (no_handler: it can
    # be replayed once a handler exists).
    source, dead = streams
    consumer = make_consumer({})
    publish(redis_client, source, dump_event(progress_event()))
    consumer.consume_once()
    [letter] = dead_letters(redis_client, dead)
    assert letter[b"reason"] == b"no_handler"
    assert pending(redis_client, source) == 0


def test_commit_failure_after_handler_rolls_back_claim(
    engine: Engine,
    make_consumer: Callable[..., Consumer],
    redis_client: Redis,
    streams: tuple[str, str],
) -> None:
    # Red when: the claim is committed before (or apart from) the handler's work, so work that
    # failed at commit is never retried; or the entry is acknowledged anyway.
    source, _ = streams
    calls: list[int] = []

    def handler(session: Session, event: Event) -> None:
        calls.append(1)
        if len(calls) == 1:
            # Breaks the outbox CHECK on event_type, which only shows at the flush in COMMIT.
            session.add(
                Outbox(
                    id=uuid.uuid4(),
                    user_id=event.user_id,
                    event_type="session.progress.v1",
                    payload={},
                    trace_context={},
                    occurred_at=NOW,
                    available_at=NOW,
                )
            )

    consumer = make_consumer({"session.progress.v1": handler})
    event = progress_event()
    publish(redis_client, source, dump_event(event))
    consumer.consume_once()
    assert not processed(engine, event.event_id)
    assert pending(redis_client, source) == 1
    consumer.consume_once()
    assert len(calls) == 2
    assert processed(engine, event.event_id)


def test_entry_trimmed_while_pending_is_dropped_without_an_ack(
    make_consumer: Callable[..., Consumer],
    redis_client: Redis,
    streams: tuple[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Red when: an entry MAXLEN trimmed away while pending stays in the pending list forever,
    # reaches a handler, or is acknowledged by hand (Redis 7 and later drop it from the pending
    # list in XAUTOCLAIM itself; an ack of an id that is gone is dead code).
    source, dead = streams
    handler = Recorder(failures=1)
    consumer = make_consumer({"session.progress.v1": handler})
    entry_id = publish(redis_client, source, dump_event(progress_event()))
    consumer.consume_once()
    redis_client.xdel(source, entry_id)
    acked: list[Any] = []
    real = redis_client.xack

    def xack(*args: Any) -> Any:
        acked.append(args)
        return real(*args)

    monkeypatch.setattr(redis_client, "xack", xack)
    assert consumer.consume_once() == []
    assert len(handler.seen) == 1
    assert pending(redis_client, source) == 0
    assert acked == []
    assert dead_letters(redis_client, dead) == []


# --- Tracing and logs ----------------------------------------------------------------------


def test_consumer_span_links_trace_context(
    make_consumer: Callable[..., Consumer],
    redis_client: Redis,
    streams: tuple[str, str],
    spans: InMemorySpanExporter,
) -> None:
    # Red when: the handler runs outside a span, or in a new trace instead of the one the
    # producer started (ADR-0013: one trace from the request to the event's handling).
    source, _ = streams
    traced: list[int] = []

    def handler(session: Session, event: Event) -> None:
        traced.append(trace.get_current_span().get_span_context().trace_id)

    consumer = make_consumer({"session.progress.v1": handler})
    event = progress_event(trace_context={"traceparent": TRACEPARENT})
    publish(redis_client, source, dump_event(event))
    consumer.consume_once()
    [span] = [s for s in spans.get_finished_spans() if s.name == SPAN_NAME]
    assert span.kind == SpanKind.CONSUMER
    assert span.parent is not None
    assert (span.parent.trace_id, span.parent.span_id) == (
        0x0AF7651916CD43DD8448EB211C80319C,
        0xB7AD6B7169203331,
    )
    assert traced == [0x0AF7651916CD43DD8448EB211C80319C]
    assert dict(span.attributes or {}) == {
        "messaging.system": "redis",
        "messaging.destination.name": source,
        "deliveries": 1,
        "event_id": str(event.event_id),
        "event_type": "session.progress.v1",
        "outcome": "processed",
    }


def test_consumer_logs_no_payload(
    make_consumer: Callable[..., Consumer],
    redis_client: Redis,
    streams: tuple[str, str],
    log_output: Callable[[], str],
) -> None:
    # Red when: a consumer log line carries the event, its user or the error's message
    # (ADR-0013: ids, counts and class names only).
    source, _ = streams

    def handler(session: Session, event: Event) -> None:
        raise Boom(f"secret {event.user_id}")

    consumer = make_consumer({"session.progress.v1": handler})
    event = progress_event()
    publish(redis_client, source, dump_event(event))
    publish(redis_client, source, "not json with secret-text")
    consumer.consume_once()
    lines = [json.loads(line) for line in log_output().splitlines()]
    mine = [line for line in lines if line["logger"] == "core_api.messaging"]
    assert {line["message"] for line in mine} == {"event handler failed", "event dead-lettered"}
    # The user is named by id on the lines of their own event (as on a request's), nowhere else.
    assert {line["user_id"] for line in mine if line["message"] == "event handler failed"} == {
        str(event.user_id)
    }
    failed = next(line for line in mine if line["message"] == "event handler failed")
    assert (failed["event_id"], failed["error_type"], failed["deliveries"]) == (
        str(event.event_id),
        "Boom",
        1,
    )
    text = log_output()
    for secret in (str(event.payload.study_session_id), "secret"):
        assert secret not in text


# --- Outages are not failures --------------------------------------------------------------


def wrapped(orig: BaseException, **kwargs: Any) -> DBAPIError:
    return OperationalError("SELECT 1", {}, orig, **kwargs)


OUTAGES = [
    pytest.param(wrapped(psycopg.OperationalError()), id="no-sqlstate"),
    pytest.param(wrapped(psycopg.errors.ConnectionFailure()), id="08006"),
    pytest.param(wrapped(psycopg.errors.AdminShutdown()), id="57P01"),
    pytest.param(wrapped(psycopg.errors.CrashShutdown()), id="57P02"),
    pytest.param(wrapped(psycopg.errors.CannotConnectNow()), id="57P03"),
    pytest.param(
        DBAPIError("SELECT 1", {}, Exception(), connection_invalidated=True), id="invalidated"
    ),
    pytest.param(RedisConnectionError(), id="redis-connection"),
    pytest.param(RedisTimeoutError(), id="redis-timeout"),
]
FAILURES = [
    pytest.param(wrapped(psycopg.errors.QueryCanceled()), id="statement-timeout"),
    pytest.param(wrapped(psycopg.errors.DeadlockDetected()), id="deadlock"),
    pytest.param(wrapped(psycopg.errors.SerializationFailure()), id="serialization"),
    pytest.param(wrapped(psycopg.errors.DiskFull()), id="disk-full"),
    pytest.param(wrapped(psycopg.errors.ProgramLimitExceeded()), id="row-too-large"),
    pytest.param(ProgrammingError("SELECT 1", {}, Exception()), id="programming-error"),
    pytest.param(ValueError("bug"), id="plain-exception"),
]


@pytest.mark.parametrize("error", OUTAGES)
def test_is_outage_only_for_a_lost_connection(error: BaseException) -> None:
    # Red when: a lost connection counts as a failed delivery.
    assert is_outage(error) is True


@pytest.mark.parametrize("error", FAILURES)
def test_is_not_outage_for_errors_that_repeat(error: BaseException) -> None:
    # Red when: a statement timeout, a deadlock, a full disk or a row too large is treated as
    # an outage, so an event that fails the same way for ever is retried for ever.
    assert is_outage(error) is False


def test_outage_in_the_handler_does_not_use_up_deliveries(
    engine: Engine,
    make_consumer: Callable[..., Consumer],
    redis_client: Redis,
    streams: tuple[str, str],
) -> None:
    # Red when: a few minutes of database downtime dead-letter every event in flight.
    source, dead = streams
    handler = Recorder()
    outages = [wrapped(psycopg.errors.AdminShutdown())] * (MAX_DELIVERIES + 3)

    def flaky(session: Session, event: Event) -> None:
        if outages:
            raise outages.pop()
        handler(session, event)

    consumer = make_consumer({"session.progress.v1": flaky})
    event = progress_event()
    publish(redis_client, source, dump_event(event))
    for _ in range(MAX_DELIVERIES + 3):
        assert consumer.consume_once() == ["unavailable"]
        assert pending(redis_client, source) == 1
    assert dead_letters(redis_client, dead) == []
    assert consumer.consume_once() == ["processed"]
    assert processed(engine, event.event_id)


@pytest.mark.parametrize("error", FAILURES)
def test_failure_that_repeats_goes_to_dead_letter_after_max_deliveries(
    make_consumer: Callable[..., Consumer],
    redis_client: Redis,
    streams: tuple[str, str],
    error: BaseException,
) -> None:
    # Red when: one of these errors is retried without limit.
    source, dead = streams

    def failing(session: Session, event: Event) -> None:
        raise error

    consumer = make_consumer({"session.progress.v1": failing})
    publish(redis_client, source, dump_event(progress_event()))
    outcomes = [consumer.consume_once() for _ in range(MAX_DELIVERIES)]
    assert outcomes == [["retry"]] * (MAX_DELIVERIES - 1) + [["dead"]]
    [letter] = dead_letters(redis_client, dead)
    assert letter[b"reason"] == type(error).__name__.encode()


def test_outage_while_checking_an_over_delivered_entry_puts_it_back(
    make_consumer: Callable[..., Consumer],
    redis_client: Redis,
    streams: tuple[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Red when: the database being down at the check dead-letters an event that may have been
    # handled already.
    source, dead = streams
    consumer = make_consumer({"session.progress.v1": Recorder()})
    publish(redis_client, source, dump_event(progress_event()))
    over_deliver(redis_client, source, MAX_DELIVERIES)

    def down(*args: Any, **kwargs: Any) -> bool:
        raise wrapped(psycopg.errors.AdminShutdown())

    monkeypatch.setattr("core_api.messaging.consumer.was_processed", down)
    assert consumer.consume_once() == ["unavailable"]
    assert dead_letters(redis_client, dead) == []
    assert pending(redis_client, source) == 1


# --- Backoff -------------------------------------------------------------------------------


def test_backoff_grows_and_stops_at_min_idle() -> None:
    # Red when: the wait between tries does not grow (5, 15, 45 s) or passes min_idle.
    assert [backoff_ms(n, base_ms=5_000, cap_ms=60_000) for n in range(1, 6)] == [
        5_000,
        15_000,
        45_000,
        60_000,
        60_000,
    ]


def spy_xclaim(redis: Redis, monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    real = redis.xclaim

    def xclaim(*args: Any, **kwargs: Any) -> Any:
        calls.append(kwargs)
        return real(*args, **kwargs)

    monkeypatch.setattr(redis, "xclaim", xclaim)
    return calls


def test_failed_entry_is_due_again_after_its_backoff_not_after_min_idle(
    make_consumer: Callable[..., Consumer], redis_client: Redis, streams: tuple[str, str]
) -> None:
    # Red when: a failed entry waits the full min_idle (no backoff), or comes back at once.
    source, _ = streams
    consumer = make_consumer(
        {"session.progress.v1": Recorder(failures=1)}, min_idle_ms=60_000, backoff_base_ms=5_000
    )
    publish(redis_client, source, dump_event(progress_event()))
    assert consumer.consume_once() == ["retry"]
    [row] = cast(list[Any], redis_client.xpending_range(source, "core-api", "-", "+", 1))
    # Counted as idle for min_idle - backoff already: due in 5 s, not in 60 s.
    assert 55_000 <= int(row["time_since_delivered"]) < 60_000
    assert int(row["times_delivered"]) == 1
    assert consumer.consume_once() == []


def test_backoff_longer_than_min_idle_never_sends_a_negative_idle(
    make_consumer: Callable[..., Consumer],
    redis_client: Redis,
    streams: tuple[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Red when: IDLE is min_idle - backoff unclamped. Redis accepts a negative IDLE (the entry
    # then looks like it will be delivered in the future), so only the value shows it.
    source, _ = streams
    calls = spy_xclaim(redis_client, monkeypatch)
    consumer = make_consumer(
        {"session.progress.v1": Recorder(failures=1)}, min_idle_ms=100, backoff_base_ms=5_000
    )
    publish(redis_client, source, dump_event(progress_event()))
    assert consumer.consume_once() == ["retry"]
    assert [call["idle"] for call in calls] == [0]


def test_deferred_by_outage_keeps_the_delivery_count(
    make_consumer: Callable[..., Consumer],
    redis_client: Redis,
    streams: tuple[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Red when: XCLAIM counts the put-back as a delivery.
    source, _ = streams
    calls = spy_xclaim(redis_client, monkeypatch)

    def down(session: Session, event: Event) -> None:
        raise wrapped(psycopg.errors.AdminShutdown())

    consumer = make_consumer({"session.progress.v1": down})
    publish(redis_client, source, dump_event(progress_event()))
    consumer.consume_once()
    [row] = cast(list[Any], redis_client.xpending_range(source, "core-api", "-", "+", 1))
    assert int(row["times_delivered"]) == 0
    assert [(c["retrycount"], c["justid"]) for c in calls] == [(0, True)]


# --- Entries that cannot be handled ---------------------------------------------------------


def over_deliver(redis: Redis, source: str, deliveries: int) -> bytes:
    """Make the only entry of `source` look delivered `deliveries` times to a consumer that
    died, so the next delivery is number `deliveries + 1`."""
    [[_, [(entry_id, _)]]] = cast(list[Any], redis.xreadgroup("core-api", "gone", {source: ">"}))
    redis.xclaim(source, "core-api", "gone", 0, [entry_id], retrycount=deliveries)
    return cast(bytes, entry_id)


def test_over_delivered_entry_already_handled_is_acknowledged(
    engine: Engine,
    make_consumer: Callable[..., Consumer],
    redis_client: Redis,
    streams: tuple[str, str],
) -> None:
    # Red when: an event that committed, whose acknowledgement was then lost again and again,
    # goes to the dead letter as if its handling had failed.
    source, dead = streams
    handler = Recorder()
    consumer = make_consumer({"session.progress.v1": handler})
    event = progress_event()
    publish(redis_client, source, dump_event(event))
    with Session(engine) as session, session.begin():
        claim(session, consumer="core-api", event_id=event.event_id, now=NOW)
    over_deliver(redis_client, source, MAX_DELIVERIES)
    assert consumer.consume_once() == ["duplicate"]
    assert handler.seen == []
    assert dead_letters(redis_client, dead) == []
    assert pending(redis_client, source) == 0


def test_over_delivered_entry_whose_record_cannot_be_read_goes_dead(
    make_consumer: Callable[..., Consumer],
    redis_client: Redis,
    streams: tuple[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Red when: a database error that is not an outage (a schema out of step) escapes the round,
    # and the entry fails every round for ever.
    source, dead = streams
    consumer = make_consumer({"session.progress.v1": Recorder()})
    publish(redis_client, source, dump_event(progress_event()))
    over_deliver(redis_client, source, MAX_DELIVERIES)

    def broken(*args: Any, **kwargs: Any) -> bool:
        raise ProgrammingError("SELECT", {}, Exception('relation "processed_event" is missing'))

    monkeypatch.setattr("core_api.messaging.consumer.was_processed", broken)
    assert consumer.consume_once() == ["dead"]
    [letter] = dead_letters(redis_client, dead)
    assert letter[b"reason"] == b"max_deliveries"


def test_entry_that_is_not_utf8_goes_to_dead_letter_and_the_next_is_handled(
    make_consumer: Callable[..., Consumer], redis_client: Redis, streams: tuple[str, str]
) -> None:
    # Red when: bytes that are not text stop the consumer, or the entries after them.
    source, dead = streams
    handler = Recorder()
    consumer = make_consumer({"session.progress.v1": handler})
    redis_client.xadd(source, {"envelope": b"\xff\xfe"})
    publish(redis_client, source, dump_event(progress_event()))
    assert consumer.consume_once() == ["dead", "processed"]
    [letter] = dead_letters(redis_client, dead)
    assert (letter[b"reason"], letter[b"envelope"]) == (b"invalid_envelope", b"\xff\xfe")


def test_event_type_outside_the_contract_is_unknown_type(
    make_consumer: Callable[..., Consumer], redis_client: Redis, streams: tuple[str, str]
) -> None:
    # Red when: a type nobody defined and a malformed known event share a reason, so a person
    # reading the dead letter cannot tell a replayable entry from a rejected one.
    source, dead = streams
    envelope = json.loads(dump_event(progress_event()))
    envelope["event_type"] = "session.shredded.v1"
    publish(redis_client, source, json.dumps(envelope))
    consumer = make_consumer({"session.progress.v1": Recorder()})
    assert consumer.consume_once() == ["dead"]
    [letter] = dead_letters(redis_client, dead)
    assert letter[b"reason"] == b"unknown_type"


EXAMPLES = Path(__file__).resolve().parents[4] / "contracts" / "events" / "examples"
VALID_EXAMPLES = sorted(p for p in EXAMPLES.glob("*.json") if ".invalid-" not in p.name)


def test_object_key_of_another_user_goes_to_dead_letter_without_the_handler(
    make_consumer: Callable[..., Consumer], redis_client: Redis, streams: tuple[str, str]
) -> None:
    # F2. Red when: user A's event, sent by a confused or hostile ai-service, makes core-api
    # take B's file as A's result.
    source, dead = streams
    other = uuid.uuid4()
    event = SessionProcessedEvent(
        event_id=uuid.uuid4(),
        event_type="session.processed.v1",
        schema_version=1,
        occurred_at=NOW,
        user_id=uuid.uuid4(),
        trace_context=TraceContext(),
        payload=SessionProcessed(
            study_session_id=uuid.uuid4(),
            run_id=uuid.uuid4(),
            result_key=f"users/{other}/subjects/s/result.json",
        ),
    )
    publish(redis_client, source, dump_event(event))
    handler = Recorder()
    consumer = make_consumer({"session.processed.v1": handler})
    assert consumer.consume_once() == ["dead"]
    assert handler.seen == []
    [letter] = dead_letters(redis_client, dead)
    assert letter[b"reason"] == b"user_mismatch"


def test_foreign_key_inside_a_list_is_caught() -> None:
    # Red when: only top-level keys are checked: note_image_keys is a list of keys.
    text = (EXAMPLES / "session.confirmed.v1.json").read_text(encoding="utf-8")
    event = json.loads(text)
    event["payload"]["note_image_keys"].append(f"users/{uuid.uuid4()}/subjects/x/notes/y/2.jpg")
    assert keys_belong_to_user(parse_event(json.dumps(event))) is False


@pytest.mark.parametrize("path", VALID_EXAMPLES, ids=lambda p: p.stem)
def test_every_object_key_in_every_example_is_checked(path: Path) -> None:
    # Red when: the check goes by field name, not type. Each key in each contract example is
    # moved to another user in turn and must be caught; an event with a key the check cannot see
    # turns this red.
    text = path.read_text(encoding="utf-8")
    event = parse_event(text)
    assert keys_belong_to_user(event) is True
    owner = f"users/{event.user_id}/"
    other = f"users/{uuid.uuid4()}/"
    count = text.count(owner)
    for index in range(count):
        head, *tail = text.split(owner)
        moved = owner.join([head, *tail[:index]]) + other + owner.join(tail[index:])
        assert moved.count(owner) == count - 1
        assert keys_belong_to_user(parse_event(moved)) is False, (path.name, index)


# --- Context, spans and the loop ------------------------------------------------------------


def test_user_does_not_leak_into_the_next_entry(
    make_consumer: Callable[..., Consumer],
    redis_client: Redis,
    streams: tuple[str, str],
    log_output: Callable[[], str],
) -> None:
    # Red when: one event's user stays in the context, and the next entry's log lines (a poison
    # entry, another user's event) are written under their name.
    source, _ = streams
    seen: list[str | None] = []

    def handler(session: Session, event: Event) -> None:
        seen.append(user_id_var.get())

    consumer = make_consumer({"session.progress.v1": handler})
    event = progress_event()
    publish(redis_client, source, dump_event(event))
    publish(redis_client, source, "poison")
    consumer.consume_once()
    assert seen == [str(event.user_id)]
    assert user_id_var.get() is None
    dead = [json.loads(line) for line in log_output().splitlines() if "event dead-lettered" in line]
    assert [line["user_id"] for line in dead] == [None]


def test_span_name_is_fixed_and_an_unparsed_entry_has_no_event_attributes(
    make_consumer: Callable[..., Consumer],
    redis_client: Redis,
    streams: tuple[str, str],
    spans: InMemorySpanExporter,
) -> None:
    # Red when: the span is named after text taken from the entry before it passed the contract,
    # or carries an event_type that anyone could have written.
    source, _ = streams
    publish(redis_client, source, json.dumps({"event_type": "a" * 500}))
    consumer = make_consumer({})
    assert consumer.consume_once() == ["dead"]
    [span] = [s for s in spans.get_finished_spans() if s.name == SPAN_NAME]
    attributes = dict(span.attributes or {})
    assert "event_type" not in attributes and "event_id" not in attributes
    assert attributes["outcome"] == "dead"


def test_pause_grows_to_a_cap() -> None:
    # Red when: a round that fails spins against a server that is down, or waits without limit.
    assert [pause_s(n) for n in range(1, 8)] == [1.0, 2.0, 4.0, 8.0, 16.0, 30.0, 30.0]


class _Scripted:
    """A consumer whose rounds do what the test says: raise, report an outage, or stop."""

    def __init__(self, stop: threading.Event, rounds: list[Any]) -> None:
        self.stop, self.rounds = stop, rounds
        self.calls = 0

    def ensure_group(self) -> None:
        pass

    def consume_once(self) -> list[str]:
        step = self.rounds[self.calls]
        self.calls += 1
        if self.calls == len(self.rounds):
            self.stop.set()
        if isinstance(step, BaseException):
            raise step
        return cast(list[str], step)


def test_run_goes_on_after_a_failed_round_and_logs_its_class_only(
    monkeypatch: pytest.MonkeyPatch, log_output: Callable[[], str]
) -> None:
    # Red when: a failed round ends the loop, or its log line carries the error's text (a
    # SQLAlchemy error holds the statement and its parameters, a traceback holds the message).
    def no_pause(failures: int) -> float:
        return 0.0

    monkeypatch.setattr("core_api.messaging.consumer.pause_s", no_pause)
    stop = threading.Event()
    scripted = _Scripted(stop, [RuntimeError("password=hunter2 refused"), ["processed"]])
    run(cast(Consumer, scripted), stop)
    assert scripted.calls == 2
    failed = [
        json.loads(line)
        for line in log_output().splitlines()
        if "event consumer round failed" in line
    ]
    assert [line["error_type"] for line in failed] == ["RuntimeError"]
    assert "hunter2" not in log_output()


def test_run_slows_down_while_the_infrastructure_is_unavailable() -> None:
    # Red when: rounds that found Redis or the database down are retried back to back.
    pauses: list[float] = []

    class Recording(threading.Event):
        def wait(self, timeout: float | None = None) -> bool:
            pauses.append(timeout or 0.0)
            return False

    stop = Recording()
    scripted = _Scripted(stop, [["unavailable"], ["unavailable"], ["processed"], []])
    run(cast(Consumer, scripted), stop)
    assert pauses == [1.0, 2.0]


# --- Lifecycle -----------------------------------------------------------------------------


def test_run_stops_when_asked(make_consumer: Callable[..., Consumer]) -> None:
    # Red when: the loop ignores the stop signal, so SIGTERM waits for Compose to kill it.
    consumer = make_consumer({}, block_ms=50)
    stop = threading.Event()
    thread, outcome = in_thread(lambda: run(consumer, stop))
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
