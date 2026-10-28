"""The `grade.requested.v1` handler (T4.19, US-05): the request file in, a result file and
`grade.completed.v1` out. Fake grader on the real test database; storage and Redis as in T4.7."""

import json
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import pytest
from jsonschema import Draft202012Validator
from redis import Redis
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from ai_service.clients.storage import StorageUnavailable
from ai_service.llm.client import LlmClient
from ai_service.llm.fake_adapter import FakeAdapter
from ai_service.llm.types import ProviderError
from ai_service.messaging.consumer import Deferred
from ai_service.messaging.envelope import GradeCompletedEvent, parse_event
from ai_service.tasks.grade import fake_grade
from ai_service.tasks.grade_async import GradeAsync, completed_event_id, result_key_for
from tests.grade.helpers import grade_body
from tests.tasks.helpers import FakeStorage

RESULT_SCHEMA: Any = Draft202012Validator(
    json.loads(
        (
            Path(__file__).resolve().parents[4]
            / "contracts"
            / "files"
            / "grade-result.v1.schema.json"
        ).read_text(encoding="utf-8")
    )
)


@pytest.fixture
def sessions(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
def stream(redis_client: Redis) -> Iterator[str]:
    name = f"test.events.ai.{uuid.uuid4()}"
    yield name
    redis_client.delete(name)


class Down:
    """A model that never answers."""

    provider = "anthropic"
    fixed_model: str | None = None
    params: dict[str, Any] = {}

    def complete(self, request: object, *, model: str, timeout: float) -> object:
        raise ProviderError("timeout")


def requested(
    storage: FakeStorage, body: dict[str, Any] | None = None, *, raw: bytes | None = None
) -> Any:
    """Put the request file in the storage and return the `grade.requested.v1` event."""
    body = body or grade_body()
    user, attempt = body["user_id"], body["attempt_id"]
    key = f"users/{user}/grading/{attempt}/request-{uuid.uuid4()}.json"
    storage.objects[key] = raw if raw is not None else json.dumps(body).encode()
    return parse_event(
        json.dumps(
            {
                "event_id": str(uuid.uuid4()),
                "event_type": "grade.requested.v1",
                "schema_version": 1,
                "occurred_at": "2026-10-28T08:30:00.000000Z",
                "user_id": user,
                "trace_context": {},
                "payload": {"attempt_id": attempt, "request_key": key},
            }
        )
    )


def handler(
    storage: FakeStorage,
    redis: Redis,
    stream: str,
    sessions: sessionmaker[Session],
    adapter: Any = None,
    *,
    disabled: bool = False,
) -> GradeAsync:
    llm = (
        None
        if disabled
        else LlmClient(
            adapter or FakeAdapter({"grade": fake_grade}),
            sessions,
            models={"grade": "claude-haiku-5-5"},
        )
    )
    return GradeAsync(storage=storage, redis=redis, llm=llm, sessions=sessions, stream=stream)


def sent(redis: Redis, stream: str) -> list[GradeCompletedEvent]:
    events = [parse_event(fields["envelope"]) for _, fields in cast(Any, redis.xrange(stream))]
    assert all(isinstance(event, GradeCompletedEvent) for event in events)
    return events  # type: ignore[return-value]


def test_grades_the_request_and_announces_the_result(
    redis_client: Redis, stream: str, sessions: sessionmaker[Session]
) -> None:
    storage = FakeStorage()
    event = requested(storage)
    handler(storage, redis_client, stream, sessions)(Session(), event)

    (completed,) = sent(redis_client, stream)
    assert completed.event_id == completed_event_id(event.event_id)
    assert completed.user_id == event.user_id
    assert completed.payload.attempt_id == event.payload.attempt_id
    assert completed.payload.result_key == result_key_for(event)
    result = json.loads(storage.objects[completed.payload.result_key])
    RESULT_SCHEMA.validate(result)
    assert result["status"] == "graded"
    assert result["response"]["provider"] == "fake"


def test_a_second_handling_pays_nothing_and_sends_the_same_event(
    redis_client: Redis, stream: str, sessions: sessionmaker[Session]
) -> None:
    storage = FakeStorage()
    event = requested(storage)
    grade = handler(storage, redis_client, stream, sessions)
    grade(Session(), event)
    before = dict(storage.objects)
    # A model that would fail if asked again: the written result is reused.
    handler(storage, redis_client, stream, sessions, Down())(Session(), event)

    assert storage.objects == before
    first, second = sent(redis_client, stream)
    assert first.event_id == second.event_id


def test_the_model_being_down_defers_without_a_result(
    redis_client: Redis, stream: str, sessions: sessionmaker[Session]
) -> None:
    storage = FakeStorage()
    event = requested(storage)
    with pytest.raises(Deferred):
        handler(storage, redis_client, stream, sessions, Down())(Session(), event)
    assert result_key_for(event) not in storage.objects
    assert sent(redis_client, stream) == []


@pytest.mark.parametrize("where", ["get", "put"])
def test_the_storage_being_down_defers(
    where: str, redis_client: Redis, stream: str, sessions: sessionmaker[Session]
) -> None:
    storage = FakeStorage()
    event = requested(storage)
    if where == "get":
        storage.get_error = StorageUnavailable()
    else:
        storage.put_error = StorageUnavailable()
    with pytest.raises(Deferred):
        handler(storage, redis_client, stream, sessions)(Session(), event)
    assert sent(redis_client, stream) == []


def failure_of(storage: FakeStorage, redis: Redis, stream: str) -> str:
    (completed,) = sent(redis, stream)
    result = json.loads(storage.objects[completed.payload.result_key])
    RESULT_SCHEMA.validate(result)
    assert result["status"] == "failed"
    return result["failure"]


def test_a_request_that_can_never_be_graded_is_a_failed_result(
    redis_client: Redis, stream: str, sessions: sessionmaker[Session]
) -> None:
    storage = FakeStorage()
    bad = grade_body(units=[])  # breaks the /v1/grade contract
    event = requested(storage, bad)
    handler(storage, redis_client, stream, sessions)(Session(), event)
    assert failure_of(storage, redis_client, stream) == "invalid"


def test_a_request_file_that_is_not_json_is_a_failed_result(
    redis_client: Redis, stream: str, sessions: sessionmaker[Session]
) -> None:
    storage = FakeStorage()
    event = requested(storage, raw=b"not json")
    handler(storage, redis_client, stream, sessions)(Session(), event)
    assert failure_of(storage, redis_client, stream) == "invalid"


def test_a_missing_request_file_is_a_failed_result(
    redis_client: Redis, stream: str, sessions: sessionmaker[Session]
) -> None:
    storage = FakeStorage()
    event = requested(storage)
    storage.objects.pop(event.payload.request_key)
    handler(storage, redis_client, stream, sessions)(Session(), event)
    assert failure_of(storage, redis_client, stream) == "invalid"


def test_a_request_of_another_user_is_not_graded(
    redis_client: Redis, stream: str, sessions: sessionmaker[Session]
) -> None:
    """F2: the file says another user or another attempt than the event does."""
    storage = FakeStorage()
    event = requested(storage)
    other = grade_body(user_id=str(uuid.uuid4()), attempt_id=str(event.payload.attempt_id))
    storage.objects[event.payload.request_key] = json.dumps(other).encode()
    handler(storage, redis_client, stream, sessions)(Session(), event)
    assert failure_of(storage, redis_client, stream) == "invalid"


def test_grading_switched_off_is_a_failed_result_not_a_wait(
    redis_client: Redis, stream: str, sessions: sessionmaker[Session]
) -> None:
    storage = FakeStorage()
    event = requested(storage)
    handler(storage, redis_client, stream, sessions, disabled=True)(Session(), event)
    assert failure_of(storage, redis_client, stream) == "disabled"
