"""T2.23, a skip racing the things it shares the session with (plan-review Y1, Y2, 🟠 locks):
a second skip, an answer being submitted, and "Dừng". Two real connections, so the setup
commits; the teardown switches the guards off to remove the rows, as in
`test_t215_submit_races.py`."""

import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import Engine, func, select, text
from sqlalchemy.orm import Session

from clock import future_exam
from core_api.api.review_sessions import stop_session
from core_api.api.units import SkipIn, skip_unit
from core_api.db.models import ReviewSession, ReviewSessionItem, User
from core_api.repositories.question import QuestionRepository, QuestionUnitRepository
from core_api.repositories.review import (
    AttemptRepository,
    QuestionNotAskableError,
    ReviewSessionItemRepository,
    ReviewSessionRepository,
)
from core_api.repositories.subject import SubjectRepository
from core_api.repositories.unit import KnowledgeUnitRepository
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
    unit_id: uuid.UUID


@pytest.fixture
def ready(engine: Engine, monkeypatch: pytest.MonkeyPatch) -> Iterator[Ready]:
    monkeypatch.setattr("core_api.domain.today.MAX_QUESTIONS", 2)
    monkeypatch.setattr("core_api.repositories.review.MAX_QUESTIONS", 2)
    with Session(engine) as session:
        user = UserRepository(session).create(f"t223-race-{uuid.uuid4()}@example.com")
        session.flush()
        subject, _ = SubjectRepository(session, user.id).create_with_exam("Mạng", future_exam())
        questions = QuestionRepository(session, user.id)
        units = KnowledgeUnitRepository(session, user.id)
        links = QuestionUnitRepository(session, user.id)
        made = []
        unit_ids = []
        for n in range(5):
            unit = units.create(
                subject.id, title=f"u{n}", summary="s", kind="concept", run_id=uuid.uuid4()
            )
            question = questions.add_idempotent(
                subject.id, level=1, prompt=f"q{n}?", reference_answer="a", run_id=uuid.uuid4()
            )
            links.link(question.id, unit.id)
            made.append(question)
            unit_ids.append(unit.id)
        review = ReviewSessionRepository(session, user.id).start(DAY, NOW)
        ReviewSessionItemRepository(session, user.id).add_all(review.id, [made[0].id, made[1].id])
        attempt = AttemptRepository(session, user.id).create_draft(review.id, made[0].id)
        state = Ready(user.id, review.id, attempt.id, unit_ids[0])
        session.commit()
    yield state
    with engine.begin() as connection:
        for table, trigger in GUARDS:
            connection.execute(text(f"ALTER TABLE {table} DISABLE TRIGGER {trigger}"))
        connection.execute(text('DELETE FROM "user" WHERE id = :id'), {"id": state.user_id})
        for table, trigger in GUARDS:
            connection.execute(text(f"ALTER TABLE {table} ENABLE TRIGGER {trigger}"))


def skip(session: Session, state: Ready) -> None:
    user = session.get(User, state.user_id)
    assert user is not None
    skip_unit(state.unit_id, SkipIn(review_session_id=state.review_id), user, session, NOW)


def items_of(engine: Engine, state: Ready) -> int:
    with Session(engine) as session:
        return (
            session.scalar(
                select(func.count())
                .select_from(ReviewSessionItem)
                .where(ReviewSessionItem.review_session_id == state.review_id)
            )
            or 0
        )


# Red when: the second skip counts before it holds the session, so it sees the unit still not
# skipped and appends a second replacement (the session passes its size).
def test_t223_two_skips_of_one_unit_add_one_replacement(engine: Engine, ready: Ready) -> None:
    with Session(engine) as first, Session(engine) as second:
        skip(first, ready)  # holds the session FOR UPDATE until commit
        pid = second.execute(text("SELECT pg_backend_pid()")).scalar_one()
        thread, outcome = in_thread(lambda: skip(second, ready))
        wait_for_lock(engine, pid, outcome)
        first.commit()
        finished(thread, outcome)
        second.commit()
    assert items_of(engine, ready) == 3  # two first ones, one replacement


# Red when: a submit that checked "askable" before the session lock goes on after the skip
# committed, so the answer of a skipped question is kept and graded.
def test_t223_a_submit_waiting_on_a_skip_finds_its_question_gone(
    engine: Engine, ready: Ready
) -> None:
    with Session(engine) as skipper, Session(engine) as submitter:
        skip(skipper, ready)
        pid = submitter.execute(text("SELECT pg_backend_pid()")).scalar_one()

        def submit() -> None:
            attempts = AttemptRepository(submitter, ready.user_id)
            attempts.save_draft(ready.attempt_id, answer_text="TCP", dont_remember=False)
            attempts.submit(ready.attempt_id, NOW)

        thread, outcome = in_thread(submit)
        wait_for_lock(engine, pid, outcome)
        skipper.commit()
        result = finished(thread, outcome)
        submitter.rollback()
    assert isinstance(result, QuestionNotAskableError)


# Red when: "Dừng" takes its count before the session lock, or ends the session while the skip
# is still appending, so the replacement is lost or the stop fails.
def test_t223_stop_waits_for_a_skip_then_ends_the_session(engine: Engine, ready: Ready) -> None:
    with Session(engine) as skipper, Session(engine) as stopper:
        skip(skipper, ready)
        pid = stopper.execute(text("SELECT pg_backend_pid()")).scalar_one()

        def stop() -> int:
            user = stopper.get(User, ready.user_id)
            assert user is not None
            return stop_session(ready.review_id, user, stopper, NOW).total

        thread, outcome = in_thread(stop)
        wait_for_lock(engine, pid, outcome)
        skipper.commit()
        total = finished(thread, outcome)
        stopper.commit()
    assert total == 2  # the skipped one is out, the replacement is in
    assert items_of(engine, ready) == 3
    with Session(engine) as session:
        ended = session.scalar(
            select(ReviewSession.ended_at).where(ReviewSession.id == ready.review_id)
        )
    assert ended is not None
