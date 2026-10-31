"""Practice attempts built through the real tables (T8.3): a question, one unit under it, and for
each attempt a review session, a submitted attempt, a grade, and `record_grade` on top."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from core_api.db.models import Attempt, Grade, Question, User
from core_api.domain.mastery import PracticeVerdict
from core_api.domain.scheduling.practice import PracticeState
from core_api.domain.scheduling.rating import Verdict
from core_api.repositories.question import QuestionUnitRepository
from core_api.repositories.review import (
    AttemptRepository,
    GradeRepository,
    ReviewSessionRepository,
)
from core_api.services.practice import record_grade
from v2_rows import RUN, make_question, make_subject, make_unit

START = datetime(2026, 10, 1, 13, 0, tzinfo=UTC)  # 20:00 in Ho Chi Minh City
OVERALL: dict[PracticeVerdict, Verdict] = {
    "correct": Verdict.CORRECT,
    "partial": Verdict.PARTIAL,
    "incorrect": Verdict.INCORRECT,
}


def day(n: int) -> datetime:
    return START + timedelta(days=n)


@dataclass
class Done:
    attempt: Attempt
    grade: Grade
    state: PracticeState


class Practice:
    """One user's questions, practised through the real tables."""

    def __init__(self, session: Session, user: User) -> None:
        self.session, self.user = session, user
        self.subject = make_subject(session, user)
        self._units: dict[uuid.UUID, uuid.UUID] = {}
        self._n = 0

    def question(self) -> Question:
        self._n += 1
        question = make_question(self.session, self.user, self.subject, n=self._n + 1000)
        unit = make_unit(self.session, self.user, self.subject)
        QuestionUnitRepository(self.session, self.user.id).link(question.id, unit.id)
        self._units[question.id] = unit.id
        return question

    def unit_of(self, question: Question) -> uuid.UUID:
        return self._units[question.id]

    def attempt(self, question: Question, at: datetime) -> Attempt:
        sessions = ReviewSessionRepository(self.session, self.user.id)
        sitting = sessions.start(at.date(), at)
        attempts = AttemptRepository(self.session, self.user.id)
        attempt = attempts.create_draft(sitting.id, question.id)
        attempts.submit(attempt.id, at)
        sessions.end(sitting.id, at, reason="completed")
        return attempt

    def grade(self, attempt: Attempt, verdict: PracticeVerdict) -> Grade:
        grade = GradeRepository(self.session, self.user.id).add_with_units(
            attempt.id,
            source="ai",
            overall=OVERALL[verdict],
            understanding=None,
            units={self._units[attempt.question_id]: OVERALL[verdict]},
            run_id=RUN,
        )
        self.session.flush()
        return grade

    def record(
        self,
        question: Question,
        grade: Grade,
        verdict: PracticeVerdict,
        at: datetime,
        *,
        active: float = 100.0,
        reference: float = 100.0,
        timing_ok: bool = True,
    ) -> PracticeState:
        return record_grade(
            self.session,
            self.user.id,
            question.id,
            grade.id,
            verdict=verdict,
            active_seconds=active,
            reference_seconds=reference,
            timing_ok=timing_ok,
            at=at,
        )

    def do(
        self,
        question: Question,
        verdict: PracticeVerdict,
        at: datetime,
        *,
        active: float = 100.0,
        reference: float = 100.0,
        timing_ok: bool = True,
    ) -> Done:
        attempt = self.attempt(question, at)
        grade = self.grade(attempt, verdict)
        state = self.record(
            question, grade, verdict, at, active=active, reference=reference, timing_ok=timing_ok
        )
        return Done(attempt, grade, state)
