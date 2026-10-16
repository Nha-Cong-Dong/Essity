"""OpenTelemetry tracing (ADR-0013).

One global TracerProvider per process, set up when the app module is imported. Spans go to the
OTLP endpoint in OTEL_EXPORTER_OTLP_ENDPOINT (the Collector); without it, spans are still
created, so log lines carry a trace_id, but nothing is exported. OTEL_SDK_DISABLED=true turns
tracing off entirely. Other OTEL_* variables work as documented by OpenTelemetry.

Span attributes must not carry personal data any more than logs may (ADR-0013). The
instrumentations record full URLs, query string included, and the ASGI one sets them after the
span has started, so cleaning them in a SpanProcessor is too early. Instead every exporter is
wrapped in `RedactingSpanExporter`, which strips query strings from the finished span before it
leaves the process. Request and response headers are not captured.
"""

import os
from collections.abc import Sequence

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter, SpanExportResult

# Attributes holding a URL or a request target, old and stable HTTP semantic conventions.
_URL_ATTRIBUTES = ("url.full", "http.url", "http.target")
_QUERY_ATTRIBUTES = ("url.query",)
REDACTED = "[redacted]"


def redact_span(span: ReadableSpan) -> ReadableSpan:
    """Copy of `span` without query strings in its URL attributes (links carry tokens)."""
    attributes = dict(span.attributes or {})
    changed = False
    for key in _URL_ATTRIBUTES:
        value = attributes.get(key)
        if isinstance(value, str) and "?" in value:
            attributes[key] = value.split("?", 1)[0]
            changed = True
    for key in _QUERY_ATTRIBUTES:
        if attributes.get(key):
            attributes[key] = REDACTED
            changed = True
    if not changed:
        return span
    return ReadableSpan(
        name=span.name,
        context=span.context,
        parent=span.parent,
        resource=span.resource,
        attributes=attributes,
        events=span.events,
        links=span.links,
        kind=span.kind,
        status=span.status,
        start_time=span.start_time,
        end_time=span.end_time,
        instrumentation_scope=span.instrumentation_scope,
    )


class RedactingSpanExporter(SpanExporter):
    """Wraps the real exporter; every span passes through `redact_span` first."""

    def __init__(self, inner: SpanExporter) -> None:
        self._inner = inner

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        return self._inner.export([redact_span(span) for span in spans])

    def shutdown(self) -> None:
        self._inner.shutdown()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return self._inner.force_flush(timeout_millis)


def configure_tracing(service: str) -> TracerProvider:
    """Install the global TracerProvider once; later calls return the existing one."""
    current = trace.get_tracer_provider()
    if isinstance(current, TracerProvider):
        return current
    provider = TracerProvider(resource=Resource.create({SERVICE_NAME: service}))
    if os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"):
        exporter = RedactingSpanExporter(OTLPSpanExporter())
        provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    return provider
