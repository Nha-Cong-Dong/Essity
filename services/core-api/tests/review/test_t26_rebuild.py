"""T2.6: memory_state (layer 4) is rebuilt from review_log (layer 3) field for field. Only each
attempt's latest grade counts (plan D7: a regrade adds rows, it never changes old ones)."""

import uuid
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy.orm import Session

from core_api.db.models import KnowledgeUnit, Question, User
from core_api.domain.scheduling.fsrs_adapter import MemoryState
from core_api.domain.scheduling.rating import ReviewRating, Verdict
from core_api.domain.scheduling.replay import schedule_review
from core_api.repositories.question import QuestionRepository, QuestionUnitRepository
from core_api.repositories.review import (
    AttemptRepository,
    GradeRepository,
    MemoryStateRepository,
    ReviewLogRepository,
    ReviewSessionRepository,
)
from core_api.repositories.subject import SubjectRepository
from core_api.repositories.unit import KnowledgeUnitRepository

RUN = uuid.uuid4()
START = datetime(2026, 10, 1, 13, 0, tzinfo=UTC)  # 20:00 in Ho Chi Minh City
EXAM = date(2026, 11, 20)
VERDICT = {
    ReviewRating.GOOD: Verdict.CORRECT,
    ReviewRating.HARD: Verdict.PARTIAL,
    ReviewRating.AGAIN: Verdict.INCORRECT,
}


class Learner:
    """One user's subjects, each with units, reviewed through the real tables; memory_state is
    written the way the live path (T2.13) will: one `schedule_review` per review."""

    def __init__(self, session: Session, user: User) -> None:
        self.session, self.user = session, user
        self.tz = ZoneInfo(user.timezone)

    def subject(self, name: str, exam: date = EXAM) -> uuid.UUID:
        subject, _ = SubjectRepository(self.session, self.user.id).create_with_exam(name, exam)
        return subject.id

    def unit(self, subject_id: uuid.UUID, title: str) -> tuple[KnowledgeUnit, Question]:
        unit = KnowledgeUnitRepository(self.session, self.user.id).create(
            subject_id, title=title, summary="s", kind="concept", run_id=RUN
        )
        question = QuestionRepository(self.session, self.user.id).add_idempotent(
            subject_id, level=1, prompt=f"{title}?", reference_answer="a", run_id=RUN
        )
        QuestionUnitRepository(self.session, self.user.id).link(question.id, unit.id)
        return unit, question

    def review(
        self, item: tuple[KnowledgeUnit, Question], rating: ReviewRating, at: datetime, exam: date
    ) -> uuid.UUID:
        unit, question = item
        sessions = ReviewSessionRepository(self.session, self.user.id)
        sitting = sessions.start(at.date(), at)
        attempts = AttemptRepository(self.session, self.user.id)
        attempt = attempts.create_draft(sitting.id, question.id)
        attempts.submit(attempt.id, at)
        self.grade(attempt.id, unit.id, rating, at, exam)
        sessions.end(sitting.id, at, reason="completed")
        return attempt.id

    def grade(
        self,
        attempt_id: uuid.UUID,
        unit_id: uuid.UUID,
        rating: ReviewRating,
        at: datetime,
        exam: date,
    ) -> None:
        grade = GradeRepository(self.session, self.user.id).add_with_units(
            attempt_id,
            source="ai",
            overall=VERDICT[rating],
            understanding=None,
            units={unit_id: VERDICT[rating]},
            run_id=RUN,
        )
        ReviewLogRepository(self.session, self.user.id).append(
            unit_id, rating=rating, reviewed_at=at, grade_id=grade.id
        )
        states = MemoryStateRepository(self.session, self.user.id)
        states.upsert(
            unit_id,
            "core",
            schedule_review(
                self.replayed_before(unit_id, at),
                rating,
                at,
                exam_day=exam,
                tz=self.tz,
                day_start_hour=self.user.day_start_hour,
            ),
        )
        self.session.flush()

    def replayed_before(self, unit_id: uuid.UUID, at: datetime) -> MemoryState | None:
        state = MemoryStateRepository(self.session, self.user.id).state(unit_id)
        return state if state is not None and state.last_review < at else None

    def states(self) -> dict[uuid.UUID, MemoryState]:
        repo = MemoryStateRepository(self.session, self.user.id)
        return {row.unit_id: repo.state(row.unit_id) for row in repo.list()}  # type: ignore[misc]


PATTERN = [ReviewRating.GOOD, ReviewRating.GOOD, ReviewRating.AGAIN, ReviewRating.HARD]


@pytest.fixture
def learner(db_session: Session, two_users: tuple[User, User]) -> Learner:
    return Learner(db_session, two_users[0])


def reviewed_history(
    learner: Learner,
    subject_id: uuid.UUID,
    units: int,
    exam: date,
    pattern: list[ReviewRating] = PATTERN,
) -> None:
    for u in range(units):
        item = learner.unit(subject_id, f"unit {u}")
        for n, rating in enumerate(pattern):
            learner.review(item, rating, START + timedelta(days=3 * n + u), exam)


# Red when: rebuild drops a field, replays in the wrong order, or skips the exam cap.
def test_t26_rebuild_matches_the_live_cache_field_for_field(learner: Learner) -> None:
    reviewed_history(learner, learner.subject("Mạng"), units=3, exam=EXAM)
    written = learner.states()
    repo = MemoryStateRepository(learner.session, learner.user.id)
    assert repo.delete_all() == 3
    assert repo.rebuild() == 3
    assert learner.states() == written


# Red when: every grade's review_log rows are replayed, not only each attempt's latest.
def test_t26_a_regrade_replaces_the_rating_it_overrides(learner: Learner) -> None:
    subject_id = learner.subject("Mạng")
    item = learner.unit(subject_id, "TCP")
    first = learner.review(item, ReviewRating.GOOD, START, EXAM)
    learner.review(item, ReviewRating.GOOD, START + timedelta(days=4), EXAM)
    # The first answer was regraded as wrong; the regrade keeps the answer's own time (D7).
    learner.grade(first, item[0].id, ReviewRating.AGAIN, START, EXAM)
    repo = MemoryStateRepository(learner.session, learner.user.id)
    repo.rebuild()
    rebuilt = repo.state(item[0].id)
    expected = None
    for rating, at in [(ReviewRating.AGAIN, START), (ReviewRating.GOOD, START + timedelta(4))]:
        expected = schedule_review(
            expected,
            rating,
            at,
            exam_day=EXAM,
            tz=learner.tz,
            day_start_hour=learner.user.day_start_hour,
        )
    assert rebuilt == expected


# US-01 AC3. Red when: a subject rebuild touches other subjects, or reads the old exam date.
def test_us01_ac3_a_subject_rebuild_uses_its_new_exam_and_leaves_the_others(
    learner: Learner,
) -> None:
    near = date(2026, 10, 20)
    moved = learner.subject("Mạng", exam=near)
    other = learner.subject("Hệ điều hành", exam=near)
    # All right: FSRS would wait weeks, so the cap at the day before the near exam is what holds
    # them; a unit relearning after a lapse is due the next day either way.
    remembered = [ReviewRating.GOOD] * 3
    reviewed_history(learner, moved, units=2, exam=near, pattern=remembered)
    reviewed_history(learner, other, units=1, exam=near, pattern=remembered)
    before = learner.states()
    SubjectRepository(learner.session, learner.user.id).update(moved, exam_date=EXAM)
    repo = MemoryStateRepository(learner.session, learner.user.id)
    assert repo.rebuild(subject_id=moved) == 2
    after = learner.states()
    moved_units = {
        u.id
        for u in KnowledgeUnitRepository(learner.session, learner.user.id).list()
        if u.subject_id == moved
    }
    for unit_id, state in after.items():
        if unit_id in moved_units:
            assert state.due > before[unit_id].due  # the cap at 19/10 is gone
        else:
            assert state == before[unit_id]


def test_t26_rebuild_is_scoped_to_one_user(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    alice, bob = (Learner(db_session, user) for user in two_users)
    reviewed_history(alice, alice.subject("Mạng"), units=1, exam=EXAM)
    reviewed_history(bob, bob.subject("Mạng"), units=1, exam=EXAM)
    alice_before = alice.states()
    bob_repo = MemoryStateRepository(db_session, bob.user.id)
    bob_repo.delete_all()
    assert bob_repo.rebuild() == 1
    assert alice.states() == alice_before


def test_t26_a_unit_with_no_reviews_gets_no_state(learner: Learner) -> None:
    learner.unit(learner.subject("Mạng"), "never asked")
    assert MemoryStateRepository(learner.session, learner.user.id).rebuild() == 0
    assert learner.states() == {}
