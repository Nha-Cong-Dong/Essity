"""T6.3: `user.deleted.v1` in ai-service deletes the user's rows and dead letters, nobody else's."""

import json
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from redis import Redis
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, sessionmaker

from ai_service.db.models import LlmCall, LlmReservation, PipelineRun
from ai_service.handlers import build_handlers
from ai_service.handlers.user_deleted import OnUserDeleted
from ai_service.messaging.envelope import parse_event
from tests.messaging.conftest import Names
from tests.messaging.helpers import publish, uploaded
from tests.messaging.test_consumer import make_consumer, pending

EXAMPLES = Path(__file__).resolve().parents[4] / "contracts" / "events" / "examples"
TABLES = (PipelineRun, LlmCall, LlmReservation)


def user_deleted(user: uuid.UUID) -> dict[str, Any]:
    event = json.loads((EXAMPLES / "user.deleted.v1.json").read_text(encoding="utf-8"))
    return {**event, "event_id": str(uuid.uuid4()), "user_id": str(user)}


def spend(sessions: sessionmaker[Session], user: uuid.UUID) -> None:
    """One run with two calls and one reservation for `user`."""
    with sessions() as session:
        run = PipelineRun(
            user_id=user,
            subject_id=uuid.uuid4(),
            task="grade",
            prompt_version="v1",
            prompt_sha256="0" * 64,
        )
        session.add(run)
        session.flush()
        for attempt in (1, 2):
            session.add(
                LlmCall(
                    pipeline_run_id=run.id,
                    user_id=user,
                    subject_id=run.subject_id,
                    task="grade",
                    provider="fake",
                    model="m",
                    prompt_version="v1",
                    attempt=attempt,
                    input={"messages": ["private notes"]},
                    cost_usd=Decimal("0.01"),
                    latency_ms=1,
                )
            )
        session.add(
            LlmReservation(
                user_id=user,
                amount_usd=Decimal("0.01"),
                expires_at=datetime.now(UTC) + timedelta(minutes=1),
            )
        )
        session.commit()


def counts(sessions: sessionmaker[Session], user: uuid.UUID) -> list[int]:
    with sessions() as session:
        return [
            session.scalar(select(func.count()).select_from(model).where(model.user_id == user))
            or 0
            for model in TABLES
        ]


def clean(sessions: sessionmaker[Session], *users: uuid.UUID) -> None:
    with sessions() as session:
        for model in (LlmCall, PipelineRun, LlmReservation):
            session.execute(delete(model).where(model.user_id.in_(users)))
        session.commit()


def run_handler(
    redis: Redis, names: Names, sessions: sessionmaker[Session], event: dict[str, Any]
) -> list[str]:
    handler = OnUserDeleted(redis=redis, dead_stream=names.dead)
    publish(redis, names.stream, event)
    consumer = make_consumer(redis, names, sessions, {"user.deleted.v1": handler})
    consumer.ensure_group()
    return consumer.run_once()


def test_t63_delete_removes_one_user_and_keeps_the_other(
    redis_client: Redis, names: Names, session_factory: sessionmaker[Session]
) -> None:
    # Red when: a delete misses a table (FK RESTRICT order) or filters on the wrong user.
    a, b = uuid.uuid4(), uuid.uuid4()
    spend(session_factory, a)
    spend(session_factory, b)
    try:
        assert run_handler(redis_client, names, session_factory, user_deleted(a)) == ["processed"]
        assert counts(session_factory, a) == [0, 0, 0]
        assert counts(session_factory, b) == [1, 2, 1]
        assert pending(redis_client, names) == 0
    finally:
        clean(session_factory, a, b)


def test_t63_handler_is_idempotent_and_unknown_user_is_fine(
    redis_client: Redis, names: Names, session_factory: sessionmaker[Session]
) -> None:
    # Red when: a second delete, or one for a user with nothing here, raises.
    a = uuid.uuid4()
    spend(session_factory, a)
    try:
        for _ in range(2):
            assert run_handler(redis_client, names, session_factory, user_deleted(a)) == [
                "processed"
            ]
        assert counts(session_factory, a) == [0, 0, 0]
        stranger = user_deleted(uuid.uuid4())
        assert run_handler(redis_client, names, session_factory, stranger) == ["processed"]
    finally:
        clean(session_factory, a)


def test_t63_handler_purges_the_dead_letter_of_the_user_only(
    redis_client: Redis, names: Names, session_factory: sessionmaker[Session]
) -> None:
    # Red when: the dead letter keeps an envelope with the user's study content, or the purge
    # removes an entry of someone who is not mentioned.
    a, b = uuid.uuid4(), uuid.uuid4()
    publish(redis_client, names.dead, uploaded(a))
    publish(redis_client, names.dead, uploaded(b))
    run_handler(redis_client, names, session_factory, user_deleted(a))
    left: list[Any] = redis_client.xrange(names.dead)  # pyright: ignore[reportAssignmentType]
    assert len(left) == 1
    assert str(b) in left[0][1]["envelope"]


def test_t63_handler_acts_on_the_envelope_user_only(
    redis_client: Redis, names: Names, session_factory: sessionmaker[Session]
) -> None:
    # Red when: the handler took a user from anywhere but `event.user_id` (the payload is empty
    # by contract), so another user's rows could go.
    a, b = uuid.uuid4(), uuid.uuid4()
    spend(session_factory, a)
    spend(session_factory, b)
    try:
        run_handler(redis_client, names, session_factory, user_deleted(a))
        assert counts(session_factory, a) == [0, 0, 0]
        assert counts(session_factory, b) == [1, 2, 1]
    finally:
        clean(session_factory, a, b)


def test_t63_handler_refuses_another_event_type() -> None:
    # Red when: wired under a wrong type it would delete for any event.
    other = parse_event(json.dumps(uploaded(uuid.uuid4())))
    with pytest.raises(TypeError):
        OnUserDeleted(redis=None, dead_stream="x")(None, other)  # pyright: ignore[reportArgumentType]


def test_t63_user_deleted_is_wired_in_build_handlers(redis_client: Redis) -> None:
    # Red when: user.deleted.v1 has no handler and goes to the dead letter as no_handler.
    handlers = build_handlers(redis=redis_client, storage=None, llm=None, sessions=None)  # pyright: ignore[reportArgumentType]
    assert isinstance(handlers["user.deleted.v1"], OnUserDeleted)


def test_t63_every_ai_table_with_a_user_id_is_covered(
    session_factory: sessionmaker[Session],
) -> None:
    # Red when: a new ai table gets a `user_id` and nobody teaches the handler to delete it.
    from ai_service.db.base import Base

    with_user = {t.name for t in Base.metadata.tables.values() if "user_id" in t.c}
    assert with_user == {model.__tablename__ for model in TABLES}
