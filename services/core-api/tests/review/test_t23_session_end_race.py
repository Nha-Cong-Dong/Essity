"""Ending a session and writing an answer to it, from two connections (plan D14, final ce93f48 #5).

Two real connections need rows both can see, so the setup commits. Its teardown has to switch off
the session trigger to remove them: the table owner can, inside the same transaction, and nothing
else runs between (T2.22: the application login cannot, so this moves to core_eraser there).
"""

import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from clock import future_exam
from core_api.repositories.question import QuestionRepository
from core_api.repositories.review import (
    AttemptRepository,
    ReviewSessionEndedError,
    ReviewSessionRepository,
)
from core_api.repositories.subject import SubjectRepository
from core_api.repositories.user import UserRepository

NOW = datetime(2026, 11, 2, 9, 0, tzinfo=UTC)
DAY = date(2026, 11, 2)
LOCK_NOT_AVAILABLE = "55P03"


@dataclass
class Open:
    user_id: uuid.UUID
    review_id: uuid.UUID
    question_id: uuid.UUID


@pytest.fixture
def open_session(engine: Engine) -> Iterator[Open]:
    with Session(engine) as session:
        user = UserRepository(session).create(f"race-{uuid.uuid4()}@example.com")
        session.flush()
        subject, _ = SubjectRepository(session, user.id).create_with_exam("Mạng", future_exam())
        question = QuestionRepository(session, user.id).add_idempotent(
            subject.id, level=1, prompt="TCP là gì?", reference_answer="a", run_id=uuid.uuid4()
        )
        review = ReviewSessionRepository(session, user.id).start(DAY, NOW)
        opened = Open(user.id, review.id, question.id)
        session.commit()
    yield opened
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE review_session DISABLE TRIGGER review_session_guard"))
        connection.execute(text('DELETE FROM "user" WHERE id = :id'), {"id": opened.user_id})
        connection.execute(text("ALTER TABLE review_session ENABLE TRIGGER review_session_guard"))


def test_us08_ending_waits_for_an_answer_being_written(engine: Engine, open_session: Open) -> None:
    # Red when: the attempt is written under the foreign key's FOR KEY SHARE only, which does not
    # stop the UPDATE of `end`, so a session could end while an answer lands in it.
    with Session(engine) as writer, Session(engine) as ender:
        AttemptRepository(writer, open_session.user_id).create_draft(
            open_session.review_id, open_session.question_id
        )
        ender.execute(text("SET LOCAL lock_timeout = '200ms'"))
        with pytest.raises(OperationalError) as refused:
            ReviewSessionRepository(ender, open_session.user_id).end(
                open_session.review_id, NOW, reason="user_stopped"
            )
        assert getattr(refused.value.orig, "sqlstate", None) == LOCK_NOT_AVAILABLE
        writer.rollback()
        ender.rollback()


def test_us08_an_answer_after_the_session_ended_is_refused(
    engine: Engine, open_session: Open
) -> None:
    with Session(engine) as ender:
        assert ReviewSessionRepository(ender, open_session.user_id).end(
            open_session.review_id, NOW, reason="completed"
        )
        ender.commit()
    with Session(engine) as writer, pytest.raises(ReviewSessionEndedError):
        AttemptRepository(writer, open_session.user_id).create_draft(
            open_session.review_id, open_session.question_id
        )
