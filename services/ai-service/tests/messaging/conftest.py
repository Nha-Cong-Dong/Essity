"""Fixtures for the event consumer's tests (T4.3): a real Redis and the real test PostgreSQL.

The test Redis is shared with other runs and never flushed: every test gets stream, group and
dead-letter names of its own, and deletes them afterwards.
"""

import uuid
from collections.abc import Iterator
from dataclasses import dataclass

import pytest
from redis import Redis
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker


@dataclass(frozen=True)
class Names:
    stream: str
    group: str
    dead: str


@pytest.fixture
def names(redis_client: Redis) -> Iterator[Names]:
    tag = uuid.uuid4()
    names = Names(
        stream=f"test.events.core.{tag}",
        group=f"test-group-{tag}",
        dead=f"test.events.dead.{tag}",
    )
    yield names
    redis_client.delete(names.stream, names.dead)


@pytest.fixture
def session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)
