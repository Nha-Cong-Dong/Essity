import os
from collections.abc import Iterator
from pathlib import Path

import pytest
import sqlalchemy
from alembic import command
from alembic.config import Config
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from redis import Redis
from sqlalchemy import Engine, text
from sqlalchemy.engine import make_url

import ai_service.main  # noqa: F401  # pyright: ignore[reportUnusedImport]  # installs tracing
from ai_service.clients.redis import redis_from_url
from ai_service.config import get_settings
from ai_service.db.engine import create_db_engine
from ai_service.telemetry import RedactingSpanExporter

TEST_SERVICE_TOKEN = "test-service-token-0123456789abcdef"
# Tests run on a real PostgreSQL, in a database of their own (`ai_test`), never on local data.
# No default: point it at a Postgres of your own (CI sets it to its service container), e.g.
# postgresql+psycopg://postgres:x@127.0.0.1:55432/ai_test. The database is created if missing.
TEST_DATABASE_URL = os.environ.get("AI_TEST_DATABASE_URL", "")
# What the app sees when the variable is missing: a valid URL nothing listens on, so tests that
# do not touch the database still run, and those that do fail in `engine` with the reason.
_UNSET_DATABASE_URL = "postgresql+psycopg://unset:unset@127.0.0.1:9/ai_test_unset"
# The event consumer's tests (T4.3) run on a real Redis. Each test uses stream names of its own
# (with a uuid), so a shared Redis is fine; never point this at a database holding real data.
TEST_REDIS_URL = os.environ.get("AI_TEST_REDIS_URL", "redis://127.0.0.1:6379/14")
SERVICE_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def service_token() -> str:
    return TEST_SERVICE_TOKEN


@pytest.fixture(autouse=True)
def service_token_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("AI_ENVIRONMENT", "test")
    monkeypatch.setenv("AI_SERVICE_TOKEN", TEST_SERVICE_TOKEN)
    monkeypatch.setenv("AI_LLM_PROVIDER", "fake")
    monkeypatch.setenv("AI_DATABASE_URL", TEST_DATABASE_URL or _UNSET_DATABASE_URL)
    # A real key in the developer's shell must never reach a test.
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def alembic_config(url: str) -> Config:
    config = Config(str(SERVICE_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(SERVICE_ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", url)
    return config


def _create_database_if_missing(url: str) -> None:
    target = make_url(url)
    server = sqlalchemy.create_engine(target.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with server.connect() as connection:
            exists = connection.scalar(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": target.database},
            )
            if not exists:
                connection.execute(text(f'CREATE DATABASE "{target.database}"'))
    finally:
        server.dispose()


@pytest.fixture(scope="session")
def test_database_url() -> str:
    if not TEST_DATABASE_URL:
        pytest.fail(
            "AI_TEST_DATABASE_URL is not set. Point it at a Postgres of your own, e.g. "
            "postgresql+psycopg://postgres:x@127.0.0.1:55432/ai_test (see README)."
        )
    return TEST_DATABASE_URL


@pytest.fixture
def alembic_cfg(test_database_url: str) -> Config:
    return alembic_config(test_database_url)


@pytest.fixture(scope="session")
def engine(test_database_url: str) -> Iterator[Engine]:
    """Engine on the test database, migrated to head once per test run."""
    _create_database_if_missing(test_database_url)
    command.upgrade(alembic_config(test_database_url), "head")
    engine = create_db_engine(test_database_url)
    yield engine
    engine.dispose()


@pytest.fixture
def redis_client() -> Iterator[Redis]:
    client = redis_from_url(TEST_REDIS_URL)
    yield client
    client.close()


@pytest.fixture(scope="session")
def exporter() -> InMemorySpanExporter:
    """One in-memory exporter on the global provider for the whole run. Added once and kept:
    the SDK cannot remove a span processor, so tests share this one and clear it (`spans`)."""
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
