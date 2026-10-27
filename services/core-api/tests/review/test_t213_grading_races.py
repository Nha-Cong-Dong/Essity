"""Grading from two connections (T2.13, plan "Giao dịch và khóa"; review T2.13 🟠1–3): one grading
per attempt, a moved exam replayed before a grade lands, two answers on one unit. Two real
connections, so the setup commits; the teardown switches the guards off to remove the rows, as in
`test_t215_submit_races.py`."""

import threading
import uuid
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import Engine, func, select, text
from sqlalchemy.orm import Session

from core_api.clients.ai_client import Graded, NotGraded
from core_api.db.models import Attempt, Grade, ReviewLog, User
from core_api.domain.grading import CheckedGrade
from core_api.domain.scheduling.rating import ReviewRating
from core_api.domain.scheduling.replay import replay
from core_api.grading import grade_attempt, record_grade
from core_api.repositories.question import QuestionRepository, QuestionUnitRepository
from core_api.repositories.review import (
    GRADING_LOCK_NAMESPACE,
    AttemptRepository,
    GradeRepository,
    MemoryStateRepository,
    ReviewSessionRepository,
)
from core_api.repositories.subject import SubjectRepository
from core_api.repositories.unit import AnchorRepository, KnowledgeUnitRepository
from core_api.repositories.user import UserRepository
from grader_stub import Stub
from races import finished, in_thread, wait_for_lock

NOW = datetime(2026, 11, 6, 9, 0, tzinfo=UTC)
DAY = date(2026, 11, 6)
FAR_EXAM = DAY + timedelta(days=60)
NEAR_EXAM = DAY + timedelta(days=1)
GUARDS = [
    ("review_session", "review_session_guard"),
    ("attempt", "attempt_guard"),
    ("grade", "grade_append_only"),
    ("grade_unit", "grade_unit_append_only"),
    ("review_log", "review_log_append_only"),
]


@dataclass
class Ready:
    user_id: uuid.UUID
    subject_id: uuid.UUID
    unit_id: uuid.UUID
    attempts: list[uuid.UUID]  # one per question, both on the one unit


@pytest.fixture
def ready(engine: Engine) -> Iterator[Ready]:
    with Session(engine) as session:
        user = UserRepository(session).create(f"t213-race-{uuid.uuid4()}@example.com")
        session.flush()
        subject, _ = SubjectRepository(session, user.id).create_with_exam("Mạng", FAR_EXAM)
        run = uuid.uuid4()
        unit = KnowledgeUnitRepository(session, user.id).create(
            subject.id, title="TCP", summary="s", kind="concept", run_id=run
        )
        AnchorRepository(session, user.id).create(
            unit.id, source="document", quote_text="TCP tin cậy", page_no=1, run_id=run
        )
        review = ReviewSessionRepository(session, user.id).start(DAY, NOW)
        attempts = AttemptRepository(session, user.id)
        made: list[uuid.UUID] = []
        for n in range(2):
            question = QuestionRepository(session, user.id).add_idempotent(
                subject.id, level=1, prompt=f"q{n}?", reference_answer="a", run_id=run
            )
            QuestionUnitRepository(session, user.id).link(question.id, unit.id)
            attempt = attempts.create_draft(review.id, question.id)
            attempts.save_draft(attempt.id, answer_text="TCP tin cậy", dont_remember=False)
            attempts.submit(attempt.id, NOW + timedelta(minutes=n))
            made.append(attempt.id)
        ready = Ready(user.id, subject.id, unit.id, made)
        session.commit()
    yield ready
    with engine.begin() as connection:
        for table, trigger in GUARDS:
            connection.execute(text(f"ALTER TABLE {table} DISABLE TRIGGER {trigger}"))
        connection.execute(text('DELETE FROM "user" WHERE id = :id'), {"id": ready.user_id})
        for table, trigger in GUARDS:
            connection.execute(text(f"ALTER TABLE {table} ENABLE TRIGGER {trigger}"))


def correct(unit_id: uuid.UUID) -> CheckedGrade:
    return CheckedGrade(
        source="ai",
        overall="correct",
        understanding=3,
        missing=[],
        units={unit_id: "correct"},
        anchors_used=[],
        run_id=None,
    )


def expected_state(session: Session, ready: Ready, exam_day: date):  # noqa: ANN201
    """The unit's state replayed in order from its review_log, with this exam date."""
    user = session.get(User, ready.user_id)
    assert user is not None
    logs = session.execute(
        select(ReviewLog.rating, ReviewLog.reviewed_at)
        .where(ReviewLog.unit_id == ready.unit_id)
        .order_by(ReviewLog.reviewed_at)
    ).all()
    return replay(
        [(ReviewRating(r), at) for r, at in logs],
        exam_day=exam_day,
        tz=ZoneInfo(user.timezone),
        day_start_hour=user.day_start_hour,
    )


class Blocking(Stub):
    """The grader, held mid-call until the test lets it answer."""

    def __init__(self) -> None:
        super().__init__()
        self.entered = threading.Event()
        self.release = threading.Event()

    def grade(self, payload: Mapping[str, object]) -> Graded | NotGraded:
        self.entered.set()
        assert self.release.wait(10)
        return super().grade(payload)


# "Chấm lại" twice (PLAN T2.13 Xong khi). Red when: grading takes no lock, so a second request
# pays the AI again and writes a second grade, or GET cannot tell a grading is under way.
def test_t213_two_regrades_one_grading(engine: Engine, ready: Ready) -> None:
    attempt_id = ready.attempts[0]
    grader = Blocking()
    with Session(engine) as first, Session(engine) as second:
        user = first.get(User, ready.user_id)
        assert user is not None

        def grade() -> object:
            outcome = grade_attempt(first, user, attempt_id, grader, environment="test")
            first.commit()
            return outcome

        thread, outcome = in_thread(grade)
        assert grader.entered.wait(10)
        other = second.get(User, ready.user_id)
        assert other is not None
        again = grade_attempt(second, other, attempt_id, grader, environment="test")
        assert again.grading == "in_progress"
        assert GradeRepository(second, ready.user_id).is_being_graded(attempt_id)
        second.rollback()
        grader.release.set()
        done = finished(thread, outcome)
        assert getattr(done, "grading", None) == "graded", done
    assert len(grader.calls) == 1
    with Session(engine) as check:
        count = check.scalar(
            select(func.count()).select_from(Grade).where(Grade.attempt_id == attempt_id)
        )
        assert count == 1
        assert not GradeRepository(check, ready.user_id).is_being_graded(attempt_id)


# PLAN T2.13 (25/10). Red when: a grade reads the exam date without holding the subject, so a
# PATCH moving the exam meanwhile is missed and the unit is scheduled by the old date.
def test_t213_exam_patch_race_schedules_by_new_date(engine: Engine, ready: Ready) -> None:
    with Session(engine) as patcher, Session(engine) as grader:
        subjects = SubjectRepository(patcher, ready.user_id)
        assert subjects.get_with_exam(ready.subject_id, lock=True) is not None
        subjects.update(ready.subject_id, exam_date=NEAR_EXAM)
        MemoryStateRepository(patcher, ready.user_id).rebuild(subject_id=ready.subject_id)
        pid = grader.execute(text("SELECT pg_backend_pid()")).scalar_one()
        user = grader.get(User, ready.user_id)
        attempt = grader.get(Attempt, ready.attempts[0])
        assert user is not None and attempt is not None

        def write() -> object:
            grade = record_grade(grader, user, attempt, correct(ready.unit_id))
            grader.commit()
            return grade

        thread, outcome = in_thread(write)
        wait_for_lock(engine, pid, outcome)
        patcher.commit()
        assert isinstance(finished(thread, outcome), Grade)
    with Session(engine) as check:
        state = MemoryStateRepository(check, ready.user_id).state(ready.unit_id)
        assert state == expected_state(check, ready, NEAR_EXAM)
        assert state != expected_state(check, ready, FAR_EXAM)  # the race is a real one


# Plan, test table "Lịch". Red when: units are not locked, so two answers on one unit each read
# the state before the other's write and one review is lost from the cache.
def test_t213_two_attempts_same_unit_no_lost_update(engine: Engine, ready: Ready) -> None:
    with Session(engine) as first, Session(engine) as second:
        user = first.get(User, ready.user_id)
        attempt = first.get(Attempt, ready.attempts[0])
        assert user is not None and attempt is not None
        record_grade(first, user, attempt, correct(ready.unit_id))  # holds the unit
        pid = second.execute(text("SELECT pg_backend_pid()")).scalar_one()
        other_user = second.get(User, ready.user_id)
        other = second.get(Attempt, ready.attempts[1])
        assert other_user is not None and other is not None

        def write() -> object:
            grade = record_grade(second, other_user, other, correct(ready.unit_id))
            second.commit()
            return grade

        thread, outcome = in_thread(write)
        wait_for_lock(engine, pid, outcome)
        first.commit()
        assert isinstance(finished(thread, outcome), Grade)
    with Session(engine) as check:
        reviews = check.scalar(
            select(func.count()).select_from(ReviewLog).where(ReviewLog.unit_id == ready.unit_id)
        )
        assert reviews == 2
        state = MemoryStateRepository(check, ready.user_id).state(ready.unit_id)
        assert state == expected_state(check, ready, FAR_EXAM)


def _attempt_with_key(session: Session, negative: bool) -> uuid.UUID:
    """An id whose lock key (a signed 64-bit hash) has the sign asked for."""
    while True:
        candidate = uuid.uuid4()
        key = session.scalar(select(func.hashtextextended(str(candidate), GRADING_LOCK_NAMESPACE)))
        assert key is not None
        if (key < 0) == negative:
            return candidate


# Review 🟢2. Red when: pg_locks is read with the halves of a negative key put back wrongly, so
# a grading under way reads as failed for about half of all attempts.
@pytest.mark.parametrize("negative", [True, False])
def test_t213_a_held_lock_is_seen_whatever_the_sign_of_its_key(
    engine: Engine, negative: bool
) -> None:
    user_id = uuid.uuid4()
    with Session(engine) as holder, Session(engine) as reader:
        attempt_id = _attempt_with_key(holder, negative)
        assert not GradeRepository(reader, user_id).is_being_graded(attempt_id)
        assert GradeRepository(holder, user_id).try_lock_attempt(attempt_id)
        assert GradeRepository(reader, user_id).is_being_graded(attempt_id)
        holder.rollback()
        assert not GradeRepository(reader, user_id).is_being_graded(attempt_id)
