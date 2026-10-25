"""Submitting while the session stops, and two tabs submitting one answer (T2.15 (a)(b), review
final #21; plan D14). Two real connections, so the setup commits; the teardown switches the
guards off to remove the rows, as in `test_t23b_subject_lock_race.py`."""

import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from clock import future_exam
from core_api.api.review_sessions import stop_session
from core_api.db.models import Attempt, User
from core_api.repositories.question import QuestionRepository
from core_api.repositories.review import (
    AttemptNotDraftError,
    AttemptRepository,
    ReviewSessionItemRepository,
    ReviewSessionRepository,
)
from core_api.repositories.subject import SubjectRepository
from core_api.repositories.user import UserRepository
from races import finished, in_thread, wait_for_lock

NOW = datetime(2026, 11, 4, 13, 0, tzinfo=UTC)
DAY = date(2026, 11, 4)
GUARDS = [
    ("review_session", "review_session_guard"),
    ("attempt", "attempt_guard"),
    ("review_session_item", "review_session_item_append_only"),
]


@dataclass
class Ready:
    user_id: uuid.UUID
    review_id: uuid.UUID
    attempt_id: uuid.UUID


@pytest.fixture
def ready(engine: Engine) -> Iterator[Ready]:
    with Session(engine) as session:
        user = UserRepository(session).create(f"t215-submit-{uuid.uuid4()}@example.com")
        session.flush()
        subject, _ = SubjectRepository(session, user.id).create_with_exam("Mạng", future_exam())
        questions = QuestionRepository(session, user.id)
        first, second = (
            questions.add_idempotent(
                subject.id, level=1, prompt=f"q{n}?", reference_answer="a", run_id=uuid.uuid4()
            )
            for n in range(2)
        )
        review = ReviewSessionRepository(session, user.id).start(DAY, NOW)
        ReviewSessionItemRepository(session, user.id).add_all(review.id, [first.id, second.id])
        attempt = AttemptRepository(session, user.id).create_draft(review.id, first.id)
        made = Ready(user.id, review.id, attempt.id)
        session.commit()
    yield made
    with engine.begin() as connection:
        for table, trigger in GUARDS:
            connection.execute(text(f"ALTER TABLE {table} DISABLE TRIGGER {trigger}"))
        connection.execute(text('DELETE FROM "user" WHERE id = :id'), {"id": made.user_id})
        for table, trigger in GUARDS:
            connection.execute(text(f"ALTER TABLE {table} ENABLE TRIGGER {trigger}"))


# (a) Red when: stop counts before taking its lock, so an answer being submitted is not counted
# and the session is closed "user_stopped" with one answered short.
def test_t29_stop_waits_for_inflight_submit_then_counts_it(engine: Engine, ready: Ready) -> None:
    with Session(engine) as submitter, Session(engine) as stopper:
        attempts = AttemptRepository(submitter, ready.user_id)
        attempts.save_draft(ready.attempt_id, answer_text="TCP", dont_remember=False)
        attempts.submit(ready.attempt_id, NOW)  # holds the session FOR SHARE until commit
        pid = stopper.execute(text("SELECT pg_backend_pid()")).scalar_one()

        def stop() -> tuple[int, int]:
            # The route itself, so its order (lock, then count) is what is tested.
            user = stopper.get(User, ready.user_id)
            assert user is not None
            out = stop_session(ready.review_id, user, stopper, NOW)
            return out.answered, out.total

        thread, outcome = in_thread(stop)
        wait_for_lock(engine, pid, outcome)
        submitter.commit()
        result = finished(thread, outcome)
        stopper.rollback()
    assert result == (1, 2)


# (b) Red when: the second tab's submit overwrites the first answer instead of finding it no
# longer a draft (the route answers that case with the first submission, 200).
def test_t29_two_tabs_submit_second_returns_first(engine: Engine, ready: Ready) -> None:
    with Session(engine) as first, Session(engine) as second:
        tab = AttemptRepository(first, ready.user_id)
        tab.save_draft(ready.attempt_id, answer_text="lần một", dont_remember=False)
        tab.submit(ready.attempt_id, NOW)
        pid = second.execute(text("SELECT pg_backend_pid()")).scalar_one()

        def submit_again() -> None:
            AttemptRepository(second, ready.user_id).submit(ready.attempt_id, NOW)

        thread, outcome = in_thread(submit_again)
        wait_for_lock(engine, pid, outcome)
        first.commit()
        result = finished(thread, outcome)
        second.rollback()
    assert isinstance(result, AttemptNotDraftError), result
    with Session(engine) as check:
        stored = check.get(Attempt, ready.attempt_id)
        assert stored is not None
        assert (stored.status, stored.answer_text) == ("submitted", "lần một")
