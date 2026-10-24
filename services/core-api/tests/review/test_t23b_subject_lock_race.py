"""Deleting a subject while an attempt is being written to it, from two connections (us-01 AC8,
T2.3b plan F3). `create_draft` holds the subject FOR SHARE; `soft_delete` locks it FOR UPDATE and
only then looks for history, so whichever commits first decides.

Two real connections need rows both can see, so the setup commits. Its teardown switches off the
session and attempt triggers to remove them, as in `test_t23_session_end_race.py` (T2.22 moves
this to core_eraser).
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
from core_api.repositories.review import AttemptRepository, ReviewSessionRepository
from core_api.repositories.subject import (
    SubjectHasHistoryError,
    SubjectNotFoundError,
    SubjectRepository,
)
from core_api.repositories.user import UserRepository
from races import finished, in_thread, wait_for_lock

NOW = datetime(2026, 11, 2, 9, 0, tzinfo=UTC)
DAY = date(2026, 11, 2)
LOCK_NOT_AVAILABLE = "55P03"
# A committed draft is guarded too: the teardown switches both off, in its own transaction.
GUARDS = [("review_session", "review_session_guard"), ("attempt", "attempt_guard")]


@dataclass
class Ready:
    user_id: uuid.UUID
    subject_id: uuid.UUID
    review_id: uuid.UUID
    question_id: uuid.UUID


@pytest.fixture
def ready(engine: Engine) -> Iterator[Ready]:
    with Session(engine) as session:
        user = UserRepository(session).create(f"t23b-race-{uuid.uuid4()}@example.com")
        session.flush()
        subject, _ = SubjectRepository(session, user.id).create_with_exam("Mạng", future_exam())
        question = QuestionRepository(session, user.id).add_idempotent(
            subject.id, level=1, prompt="TCP là gì?", reference_answer="a", run_id=uuid.uuid4()
        )
        review = ReviewSessionRepository(session, user.id).start(DAY, NOW)
        made = Ready(user.id, subject.id, review.id, question.id)
        session.commit()
    yield made
    with engine.begin() as connection:
        for table, trigger in GUARDS:
            connection.execute(text(f"ALTER TABLE {table} DISABLE TRIGGER {trigger}"))
        connection.execute(text('DELETE FROM "user" WHERE id = :id'), {"id": made.user_id})
        for table, trigger in GUARDS:
            connection.execute(text(f"ALTER TABLE {table} ENABLE TRIGGER {trigger}"))


def attempts_of(engine: Engine, user_id: uuid.UUID) -> int:
    with engine.connect() as connection:
        return connection.execute(
            text("SELECT count(*) FROM attempt WHERE user_id = :u"), {"u": user_id}
        ).scalar_one()


def test_us01_ac8_delete_waits_for_a_draft_being_inserted_then_refuses_it(
    engine: Engine, ready: Ready
) -> None:
    # Red when: `create_draft` does not hold the subject (the delete does not wait and hides a
    # subject with an attempt on it), or the history check runs before the lock or inside it
    # (its snapshot misses the attempt that commits while the delete waits).
    with Session(engine) as writer, Session(engine) as deleter:
        AttemptRepository(writer, ready.user_id).create_draft(ready.review_id, ready.question_id)
        deleter.execute(text("SET LOCAL lock_timeout = '15s'"))
        pid = deleter.execute(text("SELECT pg_backend_pid()")).scalar_one()
        thread, outcome = in_thread(
            lambda: SubjectRepository(deleter, ready.user_id).soft_delete(ready.subject_id, NOW)
        )
        wait_for_lock(engine, pid, outcome)
        writer.commit()
        result = finished(thread, outcome)
        deleter.rollback()
    assert isinstance(result, SubjectHasHistoryError), result
    assert attempts_of(engine, ready.user_id) == 1


def test_us01_ac8_a_draft_waits_while_a_delete_holds_the_subject(
    engine: Engine, ready: Ready
) -> None:
    # Red when: `create_draft` writes without asking for the subject lock.
    with Session(engine) as deleter, Session(engine) as writer:
        SubjectRepository(deleter, ready.user_id).soft_delete(ready.subject_id, NOW)
        writer.execute(text("SET LOCAL lock_timeout = '200ms'"))
        with pytest.raises(OperationalError) as refused:
            AttemptRepository(writer, ready.user_id).create_draft(
                ready.review_id, ready.question_id
            )
        assert getattr(refused.value.orig, "sqlstate", None) == LOCK_NOT_AVAILABLE
        writer.rollback()
        deleter.rollback()


def test_us01_ac8_a_draft_after_the_delete_is_refused(engine: Engine, ready: Ready) -> None:
    # Red when: `create_draft` does not check that the subject still shows (a draft would land on
    # a deleted subject).
    with Session(engine) as deleter:
        SubjectRepository(deleter, ready.user_id).soft_delete(ready.subject_id, NOW)
        deleter.commit()
    with Session(engine) as writer, pytest.raises(SubjectNotFoundError):
        AttemptRepository(writer, ready.user_id).create_draft(ready.review_id, ready.question_id)
    assert attempts_of(engine, ready.user_id) == 0
