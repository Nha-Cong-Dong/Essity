import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from core_api.config import get_settings
from core_api.db.engine import create_db_engine, get_engine

TEST_AI_SERVICE_TOKEN = "test-ai-service-token-0123456789abcdef"
# Tests run on a real PostgreSQL, in a database of their own (`core_test`), never on local data.
# CI points this at its service container; locally it is the Compose Postgres (`just up`).
TEST_DATABASE_URL = os.environ.get(
    "CORE_TEST_DATABASE_URL",
    "postgresql+psycopg://core:change-me-local@127.0.0.1:5432/core_test",
)
SERVICE_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def ai_service_token() -> str:
    return TEST_AI_SERVICE_TOKEN


@pytest.fixture(autouse=True)
def test_settings_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("CORE_AI_SERVICE_TOKEN", TEST_AI_SERVICE_TOKEN)
    monkeypatch.setenv("CORE_DATABASE_URL", TEST_DATABASE_URL)
    get_settings.cache_clear()
    get_engine.cache_clear()
    yield
    get_settings.cache_clear()
    get_engine.cache_clear()


def alembic_config(url: str = TEST_DATABASE_URL) -> Config:
    config = Config(str(SERVICE_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(SERVICE_ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", url)
    return config


@pytest.fixture
def test_database_url() -> str:
    return TEST_DATABASE_URL


@pytest.fixture
def alembic_cfg() -> Config:
    return alembic_config()


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    """Engine on the test database, migrated to head once per test run."""
    command.upgrade(alembic_config(), "head")
    engine = create_db_engine(TEST_DATABASE_URL)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(engine: Engine) -> Iterator[Session]:
    """A session whose work is rolled back after the test, whatever the test commits.

    The test runs inside an outer transaction; the session's own commits become savepoints
    within it, so the database is left exactly as it was found.
    """
    with engine.connect() as connection:
        transaction = connection.begin()
        session = Session(bind=connection, join_transaction_mode="create_savepoint")
        try:
            yield session
        finally:
            session.close()
            transaction.rollback()
