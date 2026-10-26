"""T4.4 (ADR-0006): core-api reads ai → core events from a Redis stream in a consumer group,
handles each once, retries a failing handler by redelivery and moves what cannot be handled to
the dead letter stream. Real PostgreSQL and Redis; every test has streams of its own."""

import json
import signal
import threading
import uuid
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from typing import Any, cast

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind
from redis import Redis
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from core_api.db.models import Outbox, ProcessedEvent
from core_api.messaging.consumer import (
    MAX_DELIVERIES,
    Consumer,
    Handler,
    install_signal_handlers,
    run,
)
from core_api.messaging.envelope import Event, SessionProgress, SessionProgressEvent, dump_event
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
    assert consumer.consume_once() == 2
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
    assert consumer.consume_once() == 1
    assert handler.seen == []
    assert pending(redis_client, source) == 0
    [letter] = dead_letters(redis_client, dead)
    assert (letter[b"reason"], letter[b"deliveries"]) == (b"invalid_envelope", b"1")
    assert letter[b"envelope"] == fields.get("envelope", "").encode()


def test_event_without_a_handler_goes_to_dead_letter(
    make_consumer: Callable[..., Consumer], redis_client: Redis, streams: tuple[str, str]
) -> None:
    # Red when: an event type core-api has no handler for is retried, or acknowledged silently.
    source, dead = streams
    consumer = make_consumer({})
    publish(redis_client, source, dump_event(progress_event()))
    consumer.consume_once()
    [letter] = dead_letters(redis_client, dead)
    assert letter[b"reason"] == b"unknown_type"
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


def test_entry_trimmed_while_pending_is_acknowledged(
    make_consumer: Callable[..., Consumer], redis_client: Redis, streams: tuple[str, str]
) -> None:
    # Red when: an entry MAXLEN trimmed away while pending stays in the pending list forever,
    # or crashes the consumer (plan Y1).
    source, dead = streams
    handler = Recorder(failures=1)
    consumer = make_consumer({"session.progress.v1": handler})
    entry_id = publish(redis_client, source, dump_event(progress_event()))
    consumer.consume_once()
    redis_client.xdel(source, entry_id)
    consumer.consume_once()
    assert len(handler.seen) == 1
    assert pending(redis_client, source) == 0
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
    [span] = [s for s in spans.get_finished_spans() if s.name == "consume session.progress.v1"]
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
        "messaging.message.id": str(event.event_id),
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
    failed = next(line for line in mine if line["message"] == "event handler failed")
    assert (failed["event_id"], failed["error_type"], failed["deliveries"]) == (
        str(event.event_id),
        "Boom",
        1,
    )
    text = log_output()
    for secret in (str(event.user_id), str(event.payload.study_session_id), "secret"):
        assert secret not in text


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
