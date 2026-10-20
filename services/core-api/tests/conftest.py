import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from redis import Redis
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from core_api.clients.redis import get_redis, redis_from_url
from core_api.config import get_settings
from core_api.db.engine import create_db_engine, get_engine
from core_api.db.models import User
from core_api.domain.auth.passwords import hash_password
from core_api.repositories.user import UserRepository

TEST_AI_SERVICE_TOKEN = "test-ai-service-token-0123456789abcdef"
# Tests run on a real PostgreSQL, in a database of their own (`core_test`), never on local data.
# CI points this at its service container; locally it is the Compose Postgres (`just up`).
TEST_DATABASE_URL = os.environ.get(
    "CORE_TEST_DATABASE_URL",
    "postgresql+psycopg://core:change-me-local@127.0.0.1:5432/core_test",
)
# Redis database 15 is for tests only; local data lives in database 0.
TEST_REDIS_URL = os.environ.get("CORE_TEST_REDIS_URL", "redis://127.0.0.1:6379/15")
SERVICE_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def ai_service_token() -> str:
    return TEST_AI_SERVICE_TOKEN


@pytest.fixture(autouse=True)
def test_settings_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("CORE_AI_SERVICE_TOKEN", TEST_AI_SERVICE_TOKEN)
    monkeypatch.setenv("CORE_DATABASE_URL", TEST_DATABASE_URL)
    monkeypatch.setenv("CORE_REDIS_URL", TEST_REDIS_URL)
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_redis.cache_clear()
    yield
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_redis.cache_clear()


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


@pytest.fixture
def two_users(db_session: Session) -> tuple[User, User]:
    """Alice and Bob, for isolation tests: B must never reach A's data (see isolation.py)."""
    users = UserRepository(db_session)
    alice = users.create("alice@example.com")
    bob = users.create("bob@example.com")
    db_session.flush()
    return alice, bob


@pytest.fixture
def unverified_user(db_session: Session) -> User:
    """Signed up, email never verified, password "ngựa vằn ăn cỏ buổi sáng" (T1.9, A11)."""
    user = UserRepository(db_session).create(
        "unverified@example.com", hash_password("ngựa vằn ăn cỏ buổi sáng")
    )
    db_session.flush()
    return user


@pytest.fixture
def redis_client() -> Iterator[Redis]:
    client = redis_from_url(TEST_REDIS_URL)
    yield client
    client.close()
