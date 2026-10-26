"""Fixtures for tests that commit outbox rows and relay them to a real Redis."""

import uuid
from collections.abc import Iterator

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from redis import Redis
from sqlalchemy import Engine, text


@pytest.fixture
def clean_outbox(engine: Engine) -> Iterator[None]:
    """Empty the outbox around each test: the relay sees every committed row, whoever wrote it.

    Test modules that commit rows use it with `pytestmark = pytest.mark.usefixtures(...)`.
    """

    def clean() -> None:
        with engine.begin() as connection:
            connection.execute(text("DELETE FROM outbox"))

    clean()
    yield
    clean()


@pytest.fixture
def stream(redis_client: Redis) -> Iterator[str]:
    """A stream name of this test's own: the test Redis is shared and never flushed."""
    name = f"test.events.{uuid.uuid4()}"
    yield name
    redis_client.delete(name)


@pytest.fixture
def spans() -> Iterator[InMemorySpanExporter]:
    provider = trace.get_tracer_provider()
    assert isinstance(provider, TracerProvider)  # installed when core_api.main was imported
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    yield exporter
    exporter.shutdown()
