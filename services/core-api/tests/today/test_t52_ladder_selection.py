"""T5.2 (US-03 AC3, Q19 tạm): what `TodayRepository` offers by the ladder. A unit is asked at
level 2 only after a Correct at level 1; level 3 only when every unit of the question is Correct
at level 2; the newest grade of an attempt is the one that counts. The pure rules are in
tests/domain/test_ladder.py."""

import uuid
from datetime import UTC, date, datetime

import pytest
from sqlalchemy.orm import Session
from test_t28_today_api import RUN, Space

from core_api.db.models import Question, User
from core_api.domain.ladder import LadderConfig
from core_api.domain.scheduling.rating import Verdict
from core_api.domain.today import DueUnit
from core_api.repositories.question import QuestionRepository, QuestionUnitRepository
from core_api.repositories.review import (
    AttemptRepository,
    GradeRepository,
    ReviewSessionRepository,
)
from core_api.repositories.today import TodayRepository

NOW = datetime(2026, 10, 23, 1, 0, tzinfo=UTC)
DAY = date(2026, 10, 23)


class Ladder(Space):
    """A subject whose units each have questions at several levels, and a way to answer them."""

    def __init__(self, session: Session, user: User) -> None:
        super().__init__(session, user)
        self.subject_id = self.subject()
        self.review = ReviewSessionRepository(session, user.id).start(DAY, NOW)

    def unit(self, title: str) -> uuid.UUID:
        unit_id, _ = self.question(self.subject_id, title)  # its level-1 question
        self.scheduled(unit_id, due_in_days=-1)
        return unit_id

    def asking(self, level: int, prompt: str, *units: uuid.UUID) -> Question:
        question = QuestionRepository(self.session, self.user.id).add_idempotent(
            self.subject_id, level=level, prompt=prompt, reference_answer="a", run_id=RUN
        )
        for unit in units:
            QuestionUnitRepository(self.session, self.user.id).link(question.id, unit)
        self.session.flush()
        return question

    def level_one_of(self, unit_id: uuid.UUID) -> uuid.UUID:
        return next(u.question_id for u in self.due() if u.unit_id == unit_id)

    def answer(self, question: uuid.UUID, verdict: Verdict, units: list[uuid.UUID]) -> uuid.UUID:
        """A submitted attempt with a grade; returns the attempt id."""
        attempts = AttemptRepository(self.session, self.user.id)
        attempt = attempts.create_draft(self.review.id, question)
        attempts.save_draft(attempt.id, answer_text="trả lời", dont_remember=False)
        attempts.submit(attempt.id, NOW)
        self.grade(attempt.id, verdict, units)
        return attempt.id

    def grade(self, attempt: uuid.UUID, verdict: Verdict, units: list[uuid.UUID]) -> None:
        GradeRepository(self.session, self.user.id).add_with_units(
            attempt,
            source="ai",
            overall=verdict,
            understanding=2 if verdict is Verdict.CORRECT else None,
            units=dict.fromkeys(units, verdict),
            run_id=None,
        )
        self.session.flush()

    def due(self) -> list[DueUnit]:
        return list(TodayRepository(self.session, self.user.id).scheduled_units())

    def chosen(self, unit_id: uuid.UUID) -> uuid.UUID:
        return next(u.question_id for u in self.due() if u.unit_id == unit_id)


def space(db_session: Session, two_users: tuple[User, User]) -> Ladder:
    return Ladder(db_session, two_users[0])


# US-03 AC3. Red when: level 2 is asked before a Correct at level 1, after a wrong answer, or
# is not asked after a Correct.
def test_us03_ac3_level_two_after_a_correct_at_level_one(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    s = space(db_session, two_users)
    a = s.unit("TCP")
    l1, l2 = s.level_one_of(a), s.asking(2, "TCP khi mất gói?", a)
    assert s.chosen(a) == l1
    s.answer(l1, Verdict.INCORRECT, [a])
    assert s.chosen(a) == l1
    other = s.asking(1, "TCP lần hai?", a)
    s.answer(other.id, Verdict.CORRECT, [a])
    assert s.chosen(a) == l2.id


# US-03 AC3. Red when: level 3 opens while one of its units has no Correct at level 2.
def test_us03_ac3_level_three_needs_every_unit_correct_at_level_two(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    s = space(db_session, two_users)
    a, b = s.unit("TCP"), s.unit("UDP")
    for unit in (a, b):
        s.answer(s.level_one_of(unit), Verdict.CORRECT, [unit])
    qa, qb = s.asking(2, "A2", a), s.asking(2, "B2", b)
    q3 = s.asking(3, "Vì sao UDP?", a, b)
    s.answer(qa.id, Verdict.CORRECT, [a])
    assert s.chosen(a) != q3.id and s.chosen(b) == qb.id
    s.answer(qb.id, Verdict.CORRECT, [b])
    assert s.chosen(a) == q3.id and s.chosen(b) == q3.id


# US-03 AC3. Red when: an override that turns the newest grade to incorrect still counts.
def test_us03_ac3_the_newest_grade_of_an_attempt_counts(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    s = space(db_session, two_users)
    a = s.unit("TCP")
    l1, l2 = s.level_one_of(a), s.asking(2, "TCP khi mất gói?", a)
    attempt = s.answer(l1, Verdict.CORRECT, [a])
    assert s.chosen(a) == l2.id
    s.grade(attempt, Verdict.INCORRECT, [a])
    assert s.chosen(a) == l1
    s.grade(attempt, Verdict.CORRECT, [a])
    assert s.chosen(a) == l2.id


# US-03 AC3. Red when: a new (never asked) question above level 1 is offered, or the level-1
# question of the same unit is held back with it.
def test_us03_ac3_new_questions_above_level_one_wait(
    db_session: Session, two_users: tuple[User, User]
) -> None:
    s = space(db_session, two_users)
    unit, first = s.question(s.subject_id, "UDP")  # never scheduled: a new unit
    s.asking(2, "UDP khi mất gói?", unit)
    s.asking(3, "UDP và TCP?", unit)
    reads = TodayRepository(db_session, s.user.id)
    assert {q.question_id for q in reads.new_questions()} == {first.id}


# US-03 AC3, Q19 tạm. Red when: thresholds are not read from the config: the same history under a
# stricter config keeps the unit at level 1, with no code change.
def test_us03_ac3_a_stricter_config_keeps_the_unit_at_level_one(
    db_session: Session, two_users: tuple[User, User], monkeypatch: pytest.MonkeyPatch
) -> None:
    s = space(db_session, two_users)
    a = s.unit("TCP")
    l1, l2 = s.level_one_of(a), s.asking(2, "TCP khi mất gói?", a)
    s.answer(l1, Verdict.CORRECT, [a])
    assert s.chosen(a) == l2.id
    monkeypatch.setattr(
        TodayRepository,
        "ladder",
        LadderConfig(version=2, min_correct_level1=2, min_correct_level2=1),
    )
    assert s.chosen(a) == l1
