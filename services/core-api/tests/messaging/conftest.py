"""Fixtures for tests that commit outbox rows and relay them to a real Redis."""

import uuid
from collections.abc import Iterator

import pytest
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
def stream() -> str:
    """A stream name of this test's own: the test Redis is shared and never flushed."""
    return f"test.events.{uuid.uuid4()}"
