import io
import logging
import os
import uuid
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from redis import Redis
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from core_api.api.deps import get_storage
from core_api.clients.redis import get_redis, redis_from_url
from core_api.clients.storage import S3Storage
from core_api.config import get_settings
from core_api.db.engine import create_db_engine, get_engine
from core_api.db.models import User
from core_api.db.session import get_session
from core_api.domain.auth.passwords import hash_password
from core_api.logging import configure_logging
from core_api.main import app
from core_api.repositories.user import UserRepository
from core_api.security.client_ip import CLIENT_IP_HEADER
from core_api.security.service_token import SERVICE_TOKEN_HEADER
from fake_storage import FakeStorage
from ips import fresh_ip
from object_store import (
    S3_ACCESS_KEY,
    S3_ENDPOINT,
    S3_SECRET_KEY,
    create_bucket,
    drop_bucket,
    storage_on,
)

TEST_AI_SERVICE_TOKEN = "test-ai-service-token-0123456789abcdef"
WEB_TOKEN = "test-web-token-0123456789abcdefghij"
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
    monkeypatch.setenv("CORE_ENVIRONMENT", "test")
    monkeypatch.setenv("CORE_AI_SERVICE_TOKEN", TEST_AI_SERVICE_TOKEN)
    monkeypatch.setenv("CORE_DATABASE_URL", TEST_DATABASE_URL)
    monkeypatch.setenv("CORE_REDIS_URL", TEST_REDIS_URL)
    # The shared S3_* names (.env.example); API tests swap in a storage of their own.
    monkeypatch.setenv("S3_ENDPOINT", S3_ENDPOINT)
    monkeypatch.setenv("S3_PUBLIC_ENDPOINT", "")
    monkeypatch.setenv("S3_BUCKET", "essity-test-unused")
    monkeypatch.setenv("S3_ACCESS_KEY", S3_ACCESS_KEY)
    monkeypatch.setenv("S3_SECRET_KEY", S3_SECRET_KEY)
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


# --- The real app over HTTP, its requests in the test's rolled-back session. Each test comes
# from an IP of its own: rate limits are per IP and the test Redis is shared.


@pytest.fixture
def client_ip() -> str:
    return fresh_ip("10")


@pytest.fixture
def client(
    db_session: Session, monkeypatch: pytest.MonkeyPatch, client_ip: str
) -> Iterator[TestClient]:
    monkeypatch.setenv("CORE_WEB_TOKEN", WEB_TOKEN)
    get_settings.cache_clear()

    def session_override() -> Iterator[Session]:
        yield db_session
        db_session.flush()

    app.dependency_overrides[get_session] = session_override
    # Grading queues its request in the storage (T4.19); a double, unless a test brings its own.
    app.dependency_overrides.setdefault(get_storage, lambda: FakeStorage())
    headers = {SERVICE_TOKEN_HEADER: WEB_TOKEN, CLIENT_IP_HEADER: client_ip}
    yield TestClient(app, headers=headers)
    app.dependency_overrides.pop(get_session)
    app.dependency_overrides.pop(get_storage, None)


@pytest.fixture
def log_output() -> Iterator[Callable[[], str]]:
    root = logging.getLogger()
    saved = (root.handlers[:], root.level)
    buffer = io.StringIO()
    configure_logging("core-api", "DEBUG", stream=buffer)
    yield buffer.getvalue
    root.handlers, root.level = saved


# --- The real object store (T4.5): a bucket of this run's own, see object_store.py.


@pytest.fixture(scope="session")
def s3_bucket() -> Iterator[str]:
    bucket = create_bucket()
    yield bucket
    drop_bucket(bucket)


@pytest.fixture
def s3_storage(s3_bucket: str) -> S3Storage:
    return storage_on(s3_bucket)


@pytest.fixture
def object_key() -> str:
    """A key no other test uses: the bucket is shared by the whole run."""
    return f"users/{uuid.uuid4()}/subjects/{uuid.uuid4()}/raw/{uuid.uuid4().hex}.pdf"
