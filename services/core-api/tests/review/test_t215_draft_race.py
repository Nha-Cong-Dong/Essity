"""Two tabs opening the same question at once (T2.15 (c), PM gate #21): the second insert waits on
UNIQUE(review_session_id, question_id), then returns the first draft instead of failing with 500.
React StrictMode runs the answer screen's effect twice in development, so this is the normal case
there. Two real connections, so the setup commits; the teardown switches the guards off to remove
the rows, as in `test_t23b_subject_lock_race.py` (T2.22 moves this to core_eraser)."""

import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from clock import future_exam
from core_api.db.models import Attempt
from core_api.repositories.question import QuestionRepository
from core_api.repositories.review import AttemptRepository, ReviewSessionRepository
from core_api.repositories.subject import SubjectRepository
from core_api.repositories.user import UserRepository
from races import finished, in_thread, wait_for_lock

NOW = datetime(2026, 11, 3, 13, 0, tzinfo=UTC)
DAY = date(2026, 11, 3)
GUARDS = [("review_session", "review_session_guard"), ("attempt", "attempt_guard")]


@dataclass
class Ready:
    user_id: uuid.UUID
    review_id: uuid.UUID
    question_id: uuid.UUID


@pytest.fixture
def ready(engine: Engine) -> Iterator[Ready]:
    with Session(engine) as session:
        user = UserRepository(session).create(f"t215-race-{uuid.uuid4()}@example.com")
        session.flush()
        subject, _ = SubjectRepository(session, user.id).create_with_exam("Mạng", future_exam())
        question = QuestionRepository(session, user.id).add_idempotent(
            subject.id, level=1, prompt="TCP là gì?", reference_answer="a", run_id=uuid.uuid4()
        )
        review = ReviewSessionRepository(session, user.id).start(DAY, NOW)
        made = Ready(user.id, review.id, question.id)
        session.commit()
    yield made
    with engine.begin() as connection:
        for table, trigger in GUARDS:
            connection.execute(text(f"ALTER TABLE {table} DISABLE TRIGGER {trigger}"))
        connection.execute(text('DELETE FROM "user" WHERE id = :id'), {"id": made.user_id})
        for table, trigger in GUARDS:
            connection.execute(text(f"ALTER TABLE {table} ENABLE TRIGGER {trigger}"))


# Red when: the second insert raises IntegrityError (a 500 at the route), or makes a second draft.
def test_t215_two_tabs_opening_one_question_get_one_draft(engine: Engine, ready: Ready) -> None:
    with Session(engine) as first, Session(engine) as second:
        made, created = AttemptRepository(first, ready.user_id).open_draft(
            ready.review_id, ready.question_id
        )
        assert created
        pid = second.execute(text("SELECT pg_backend_pid()")).scalar_one()
        thread, outcome = in_thread(
            lambda: AttemptRepository(second, ready.user_id).open_draft(
                ready.review_id, ready.question_id
            )
        )
        wait_for_lock(engine, pid, outcome)
        first.commit()
        result = finished(thread, outcome)
        assert not isinstance(result, BaseException), result
        found, created_again = result  # type: ignore[misc]
        assert (found.id, created_again) == (made.id, False)  # type: ignore[union-attr]
        second.commit()
    with Session(engine) as check:
        count = check.query(Attempt).filter(Attempt.user_id == ready.user_id).count()
    assert count == 1
