"""Fixtures for the account endpoints: the real app, its requests running in the test's
rolled-back session, each test coming from an IP of its own (rate limits are per IP and the
test Redis is shared)."""

import io
import logging
import random
from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from core_api.config import get_settings
from core_api.db.session import get_session
from core_api.logging import configure_logging
from core_api.main import app
from core_api.security.client_ip import CLIENT_IP_HEADER
from core_api.security.service_token import SERVICE_TOKEN_HEADER

WEB_TOKEN = "test-web-token-0123456789abcdefghij"


@pytest.fixture
def client_ip() -> str:
    return f"10.{random.randrange(256)}.{random.randrange(256)}.{random.randrange(1, 255)}"


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
    headers = {SERVICE_TOKEN_HEADER: WEB_TOKEN, CLIENT_IP_HEADER: client_ip}
    yield TestClient(app, headers=headers)
    app.dependency_overrides.pop(get_session)


@pytest.fixture
def log_output() -> Iterator[Callable[[], str]]:
    root = logging.getLogger()
    saved = (root.handlers[:], root.level)
    buffer = io.StringIO()
    configure_logging("core-api", "DEBUG", stream=buffer)
    yield buffer.getvalue
    root.handlers, root.level = saved
