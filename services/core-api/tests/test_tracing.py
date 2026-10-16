import io
import json
import logging
from collections.abc import Iterator

import httpx2
import pytest
from fastapi.testclient import TestClient
from opentelemetry import trace
from opentelemetry.instrumentation.httpx import HTTPX2ClientInstrumentor
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind
from opentelemetry.trace.status import Status
from sqlalchemy import Engine, text

from core_api.api.ping import get_ai_client
from core_api.clients.ai_client import AiServiceClient
from core_api.config import get_settings
from core_api.db.engine import create_db_engine
from core_api.logging import configure_logging
from core_api.main import app
from core_api.telemetry import REDACTED, RedactingSpanExporter, redact_span

SECRET = "token-that-must-not-be-traced"


@pytest.fixture(scope="session")
def exporter() -> InMemorySpanExporter:
    provider = trace.get_tracer_provider()
    assert isinstance(provider, TracerProvider)  # installed when core_api.main was imported
    exporter = InMemorySpanExporter()
    # Same wrapper as configure_tracing puts around the OTLP exporter.
    provider.add_span_processor(SimpleSpanProcessor(RedactingSpanExporter(exporter)))
    return exporter


@pytest.fixture
def spans(exporter: InMemorySpanExporter) -> Iterator[InMemorySpanExporter]:
    exporter.clear()
    yield exporter
    exporter.clear()


@pytest.fixture
def ai_requests() -> Iterator[list[httpx2.Request]]:
    """Point /v1/ping at a fake ai-service and record what core-api sends it."""
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(200, json={"status": "ok"})

    ai_client = AiServiceClient.from_settings(get_settings(), httpx2.MockTransport(handler))
    app.dependency_overrides[get_ai_client] = lambda: ai_client
    yield seen
    app.dependency_overrides.clear()
    ai_client.close()


def by_kind(spans: InMemorySpanExporter, kind: SpanKind) -> list[ReadableSpan]:
    return [span for span in spans.get_finished_spans() if span.kind == kind]


def attribute_text(spans: InMemorySpanExporter) -> str:
    return json.dumps([dict(span.attributes or {}) for span in spans.get_finished_spans()])


def test_ping_is_one_trace_with_a_client_span_to_ai_service(
    spans: InMemorySpanExporter, ai_requests: list[httpx2.Request]
) -> None:
    assert TestClient(app).get("/v1/ping").status_code == 200
    [server] = by_kind(spans, SpanKind.SERVER)
    [client] = by_kind(spans, SpanKind.CLIENT)
    assert server.name == "GET /v1/ping"
    assert server.context is not None and client.context is not None
    assert client.context.trace_id == server.context.trace_id
    assert client.parent is not None and client.parent.span_id == server.context.span_id


def test_trace_context_is_sent_to_ai_service(
    spans: InMemorySpanExporter, ai_requests: list[httpx2.Request]
) -> None:
    TestClient(app).get("/v1/ping")
    [client] = by_kind(spans, SpanKind.CLIENT)
    assert client.context is not None
    version, trace_id, span_id, _ = ai_requests[0].headers["traceparent"].split("-")
    assert version == "00"
    assert trace_id == format(client.context.trace_id, "032x")
    assert span_id == format(client.context.span_id, "016x")


def test_healthz_is_not_traced(spans: InMemorySpanExporter) -> None:
    TestClient(app).get("/healthz")
    assert spans.get_finished_spans() == ()


def test_query_string_is_not_in_server_span(
    spans: InMemorySpanExporter, ai_requests: list[httpx2.Request]
) -> None:
    TestClient(app).get(f"/v1/ping?token={SECRET}")
    assert SECRET not in attribute_text(spans)
    [server] = by_kind(spans, SpanKind.SERVER)
    query = (server.attributes or {}).get("url.query")
    assert query in (None, REDACTED)


def test_query_string_is_not_in_client_span(spans: InMemorySpanExporter) -> None:
    transport = httpx2.MockTransport(lambda request: httpx2.Response(200))
    with httpx2.Client(base_url="http://ai-service:8001", transport=transport) as http:
        HTTPX2ClientInstrumentor.instrument_client(http)  # pyright: ignore[reportUnknownMemberType]
        http.get(f"/v1/ping?code={SECRET}")
    [client] = by_kind(spans, SpanKind.CLIENT)
    assert SECRET not in attribute_text(spans)
    url = (client.attributes or {}).get("url.full") or (client.attributes or {}).get("http.url")
    assert url == "http://ai-service:8001/v1/ping"


def test_log_lines_inside_a_request_carry_its_trace_id(
    spans: InMemorySpanExporter, ai_requests: list[httpx2.Request]
) -> None:
    root = logging.getLogger()
    saved = (root.handlers[:], root.level)
    buffer = io.StringIO()
    configure_logging("core-api", "INFO", stream=buffer)
    try:
        TestClient(app).get("/v1/ping")
    finally:
        root.handlers, root.level = saved
    [access] = [
        json.loads(line)
        for line in buffer.getvalue().splitlines()
        if json.loads(line)["logger"] == "core_api.access"
    ]
    [server] = by_kind(spans, SpanKind.SERVER)
    assert server.context is not None
    assert access["trace_id"] == format(server.context.trace_id, "032x")


def test_log_lines_outside_a_trace_have_no_trace_id() -> None:
    root = logging.getLogger()
    saved = (root.handlers[:], root.level)
    buffer = io.StringIO()
    configure_logging("core-api", "INFO", stream=buffer)
    try:
        logging.getLogger("core_api.test").info("startup")
    finally:
        root.handlers, root.level = saved
    assert "trace_id" not in json.loads(buffer.getvalue())


def test_redact_span_strips_queries_and_keeps_everything_else() -> None:
    span = ReadableSpan(
        name="GET /verify",
        attributes={
            "url.full": f"https://essity.app/verify?token={SECRET}",
            "http.target": f"/verify?token={SECRET}",
            "url.query": f"token={SECRET}",
            "http.status_code": 200,
        },
        kind=SpanKind.SERVER,
        status=Status(),
        start_time=1,
        end_time=2,
    )
    redacted = redact_span(span)
    assert dict(redacted.attributes or {}) == {
        "url.full": "https://essity.app/verify",
        "http.target": "/verify",
        "url.query": REDACTED,
        "http.status_code": 200,
    }
    assert (redacted.name, redacted.kind, redacted.start_time, redacted.end_time) == (
        "GET /verify",
        SpanKind.SERVER,
        1,
        2,
    )


def test_redact_span_returns_clean_spans_unchanged() -> None:
    span = ReadableSpan(name="GET /v1/ping", attributes={"url.full": "http://x/v1/ping"})
    assert redact_span(span) is span


def test_database_queries_are_traced(
    spans: InMemorySpanExporter, engine: Engine, test_database_url: str
) -> None:
    # Guards the SQLAlchemy pin: on an unsupported version the instrumentation does nothing.
    traced = create_db_engine(test_database_url)
    with traced.connect() as connection:
        connection.execute(text("SELECT 1"))
    traced.dispose()
    statements = [
        str((s.attributes or {}).get("db.statement")) for s in by_kind(spans, SpanKind.CLIENT)
    ]
    assert "SELECT 1" in statements
