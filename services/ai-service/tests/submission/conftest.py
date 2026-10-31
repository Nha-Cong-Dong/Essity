"""Fixtures of the submission handler's tests: a stream of its own, a session factory, a clean audit
table for the test user (rows with the new tasks would stop the migration down-and-up test)."""

import uuid
from collections.abc import Iterator

import pytest
from redis import Redis
from sqlalchemy import Engine, delete
from sqlalchemy.orm import Session, sessionmaker

from ai_service.db.models import LlmCall, PipelineRun
from tests.submission.helpers import USER


@pytest.fixture
def sessions(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)


@pytest.fixture(autouse=True)
def clean_audit(sessions: sessionmaker[Session]) -> Iterator[None]:
    for step in range(2):
        with sessions.begin() as s:
            s.execute(delete(LlmCall).where(LlmCall.user_id == USER))
            s.execute(delete(PipelineRun).where(PipelineRun.user_id == USER))
        if step == 0:
            yield


@pytest.fixture
def stream(redis_client: Redis) -> Iterator[str]:
    name = f"test.events.ai.{uuid.uuid4()}"
    yield name
    redis_client.delete(name)
