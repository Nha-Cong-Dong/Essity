import json
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from opentelemetry import trace
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind

from ai_service.main import create_app
from ai_service.security import SERVICE_TOKEN_HEADER
from ai_service.telemetry import RedactingSpanExporter

TRACE_ID = "4bf92f3577b34da6a3ce929d0e0e4736"
PARENT_SPAN_ID = "00f067aa0ba902b7"
SECRET = "token-that-must-not-be-traced"


@pytest.fixture(scope="session")
def exporter() -> InMemorySpanExporter:
    provider = trace.get_tracer_provider()
    assert isinstance(provider, TracerProvider)  # installed when ai_service.main was imported
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(RedactingSpanExporter(exporter)))
    return exporter


@pytest.fixture
def spans(exporter: InMemorySpanExporter) -> Iterator[InMemorySpanExporter]:
    exporter.clear()
    yield exporter
    exporter.clear()


def server_span(spans: InMemorySpanExporter) -> ReadableSpan:
    [span] = [s for s in spans.get_finished_spans() if s.kind == SpanKind.SERVER]
    return span


def test_ping_continues_the_trace_started_by_core_api(
    spans: InMemorySpanExporter, service_token: str
) -> None:
    response = TestClient(create_app()).get(
        "/v1/ping",
        headers={
            SERVICE_TOKEN_HEADER: service_token,
            "traceparent": f"00-{TRACE_ID}-{PARENT_SPAN_ID}-01",
        },
    )
    assert response.status_code == 200
    span = server_span(spans)
    assert span.context is not None and span.parent is not None
    assert format(span.context.trace_id, "032x") == TRACE_ID
    assert format(span.parent.span_id, "016x") == PARENT_SPAN_ID
    assert span.parent.is_remote


def test_rejected_request_is_traced_too(spans: InMemorySpanExporter) -> None:
    assert TestClient(create_app()).get("/v1/ping").status_code == 401
    assert (server_span(spans).attributes or {}).get("http.status_code") == 401


def test_query_string_is_not_in_span(spans: InMemorySpanExporter, service_token: str) -> None:
    TestClient(create_app()).get(
        f"/v1/ping?token={SECRET}", headers={SERVICE_TOKEN_HEADER: service_token}
    )
    attributes = json.dumps([dict(s.attributes or {}) for s in spans.get_finished_spans()])
    assert SECRET not in attributes


def test_healthz_is_not_traced(spans: InMemorySpanExporter) -> None:
    TestClient(create_app()).get("/healthz")
    assert spans.get_finished_spans() == ()
