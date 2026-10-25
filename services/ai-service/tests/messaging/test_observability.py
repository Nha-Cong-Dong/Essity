"""T4.3: the consumer continues core-api's trace and logs ids and outcomes only (ADR-0013)."""

import io
import json
import logging
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind, StatusCode
from redis import Redis
from sqlalchemy.orm import Session, sessionmaker

from ai_service.logging import configure_logging, user_id_var
from tests.messaging.conftest import Names
from tests.messaging.helpers import (
    DOCUMENT_UPLOADED,
    PARENT_SPAN_ID,
    SECRET_DETAIL,
    TRACE_ID,
    Recorder,
    boom,
    publish,
    uploaded,
)
from tests.messaging.test_consumer import make_consumer

Lines = Callable[[], list[dict[str, Any]]]
SPAN_NAME = "events.core process"


@pytest.fixture
def log_lines() -> Iterator[Lines]:
    root = logging.getLogger()
    saved = (root.handlers[:], root.level, logging.getLogger("uvicorn.access").disabled)
    buffer = io.StringIO()
    configure_logging("ai-consumer", "INFO", stream=buffer)

    def lines() -> list[dict[str, Any]]:
        parsed = [json.loads(line) for line in buffer.getvalue().splitlines()]
        return [line for line in parsed if line["logger"] == "ai_service.messaging"]

    yield lines
    root.handlers, root.level, logging.getLogger("uvicorn.access").disabled = saved


def consumer_spans(spans: InMemorySpanExporter) -> list[ReadableSpan]:
    return [span for span in spans.get_finished_spans() if span.name == SPAN_NAME]


def test_t43_consumer_span_continues_trace_context(
    redis_client: Redis,
    names: Names,
    session_factory: sessionmaker[Session],
    spans: InMemorySpanExporter,
) -> None:
    # Red when: the span starts a new trace, and Jaeger shows the upload and its processing apart.
    event = uploaded()
    publish(redis_client, names.stream, event)
    consumer = make_consumer(redis_client, names, session_factory, {DOCUMENT_UPLOADED: Recorder()})
    consumer.ensure_group()
    consumer.run_once()
    [span] = consumer_spans(spans)
    assert span.kind == SpanKind.CONSUMER
    assert span.context is not None and span.parent is not None
    assert format(span.context.trace_id, "032x") == TRACE_ID
    assert format(span.parent.span_id, "016x") == PARENT_SPAN_ID
    assert dict(span.attributes or {}) == {
        "event_id": event["event_id"],
        "event_type": DOCUMENT_UPLOADED,
        "deliveries": 1,
        "outcome": "processed",
    }
    # The handler's database queries are children of the consumer span.
    children = [
        s
        for s in spans.get_finished_spans()
        if s.parent and s.parent.span_id == span.context.span_id
    ]
    assert children


def test_t43_event_without_trace_context_starts_a_new_trace(
    redis_client: Redis,
    names: Names,
    session_factory: sessionmaker[Session],
    spans: InMemorySpanExporter,
) -> None:
    publish(redis_client, names.stream, uploaded(traceparent=None))
    consumer = make_consumer(redis_client, names, session_factory, {DOCUMENT_UPLOADED: Recorder()})
    consumer.ensure_group()
    consumer.run_once()
    [span] = consumer_spans(spans)
    assert span.parent is None


def test_t43_poison_entry_span_has_no_unchecked_attributes(
    redis_client: Redis,
    names: Names,
    session_factory: sessionmaker[Session],
    spans: InMemorySpanExporter,
) -> None:
    # Review 🟡6: an event_type that failed the contract is any string; it stays out of spans.
    publish(redis_client, names.stream, {**uploaded(), "event_type": "x" * 5000})
    consumer = make_consumer(redis_client, names, session_factory, {DOCUMENT_UPLOADED: Recorder()})
    consumer.ensure_group()
    consumer.run_once()
    [span] = consumer_spans(spans)
    assert span.parent is None
    assert dict(span.attributes or {}) == {"deliveries": 1, "outcome": "dead"}
    assert span.status.status_code == StatusCode.ERROR


def test_t43_consumer_logs_and_spans_carry_no_payload_or_exception_message(
    redis_client: Redis,
    names: Names,
    session_factory: sessionmaker[Session],
    spans: InMemorySpanExporter,
    log_lines: Lines,
) -> None:
    # ADR-0013. Red when: an exception is recorded on the span or logged with its message, or
    # the envelope (object keys, ids of the user's files) is logged.
    event = uploaded()
    publish(redis_client, names.stream, event)
    consumer = make_consumer(
        redis_client, names, session_factory, {DOCUMENT_UPLOADED: Recorder(fail_with=boom)}
    )
    consumer.ensure_group()
    consumer.run_once()
    [line] = log_lines()
    assert line["outcome"] == "retry"
    assert line["error_type"] == "Boom"
    assert line["event_id"] == event["event_id"]
    assert line["event_type"] == DOCUMENT_UPLOADED
    assert line["deliveries"] == 1
    assert line["user_id"] == event["user_id"]
    assert "dropped_fields" not in line
    written = json.dumps(log_lines(), ensure_ascii=False)
    assert SECRET_DETAIL not in written
    assert event["payload"]["object_key"] not in written
    [span] = consumer_spans(spans)
    assert span.status.status_code == StatusCode.ERROR
    assert span.status.description is None
    assert not span.events  # no recorded exception
    assert "user_id" not in (span.attributes or {})


def test_t43_dead_letter_is_logged_with_its_reason(
    redis_client: Redis, names: Names, session_factory: sessionmaker[Session], log_lines: Lines
) -> None:
    publish(redis_client, names.stream, "not json")
    consumer = make_consumer(redis_client, names, session_factory, {DOCUMENT_UPLOADED: Recorder()})
    consumer.ensure_group()
    consumer.run_once()
    [line] = log_lines()
    assert (line["level"], line["outcome"], line["reason"]) == ("ERROR", "dead", "invalid_envelope")
    assert "event_id" not in line


def test_t43_user_id_does_not_leak_to_next_entry(
    redis_client: Redis, names: Names, session_factory: sessionmaker[Session], log_lines: Lines
) -> None:
    # Review 🟡5. Red when: the user of one event stays in the context, and the next entry's
    # log lines (a poison entry, another user's event) are written under their name.
    event = uploaded()
    publish(redis_client, names.stream, event)
    publish(redis_client, names.stream, "not json")
    consumer = make_consumer(redis_client, names, session_factory, {DOCUMENT_UPLOADED: Recorder()})
    consumer.ensure_group()
    consumer.run_once()
    first, second = log_lines()
    assert first["user_id"] == event["user_id"]
    assert second["user_id"] is None
    assert user_id_var.get() is None
