"""Record a graded practice attempt in the question's own FSRS schedule (T8.3, ADR-0029).

Practice never writes `review_log` or `memory_state`: the two schedules are independent.
The caller (the grading path, T8.4) commits and turns a "forgot" answer into `incorrect`.
"""

import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from core_api.domain.mastery import (
    DEFAULT_CONFIG,
    MasteryConfig,
    PracticeVerdict,
    rating_for,
)
from core_api.domain.scheduling.practice import PracticeState, verdict_of
from core_api.repositories.practice import PracticeLogRepository, PracticeStateRepository
from core_api.repositories.question import QuestionNotFoundError
from core_api.repositories.review import AttemptRepository, GradeRepository

__all__ = [
    "GradeMismatchError",
    "QuestionNotFoundError",
    "readd",
    "record_grade",
    "remove",
]


class GradeMismatchError(ValueError):
    """The grade is not this user's, or is not a grade of an attempt at this question."""


def record_grade(
    session: Session,
    user_id: uuid.UUID,
    question_id: uuid.UUID,
    grade_id: uuid.UUID,
    *,
    verdict: PracticeVerdict,
    active_seconds: float,
    reference_seconds: float,
    timing_ok: bool,
    at: datetime,
    config: MasteryConfig = DEFAULT_CONFIG,
) -> PracticeState:
    """One log row for the grade, then the question's state rebuilt from its log, in the caller's
    transaction. The first attempt creates the state; the same grade twice changes nothing.

    The state is always rebuilt, not stepped: a regrade of an older attempt or a grade that
    arrives late must give the same state a replay gives (US-06 AC7, US-16 AC10)."""
    states = PracticeStateRepository(session, user_id)
    log = PracticeLogRepository(session, user_id)
    states.hold_question(question_id)
    grade = GradeRepository(session, user_id).get(grade_id)
    attempt = AttemptRepository(session, user_id).get(grade.attempt_id) if grade else None
    if grade is None or attempt is None or attempt.question_id != question_id:
        raise GradeMismatchError(grade_id)
    if log.by_grade(grade_id) is None:
        earlier = [
            r
            for r in log.effective([question_id])
            if r.attempt_id != grade.attempt_id and r.reviewed_at <= at
        ]
        previous = verdict_of(earlier[-1].rating) if earlier else None
        rating = rating_for(verdict, active_seconds, reference_seconds, previous, timing_ok, config)
        log.append(question_id, rating=rating, reviewed_at=at, grade_id=grade_id)
        states.rebuild([question_id])
    state = states.state(question_id)
    assert state is not None
    return state


def remove(session: Session, user_id: uuid.UUID, question_id: uuid.UUID, at: datetime) -> bool:
    """Stop the question's schedule. False for a question never attempted: it has no state."""
    states = PracticeStateRepository(session, user_id)
    states.hold_question(question_id)
    return states.set_removed_at(question_id, at)


def readd(session: Session, user_id: uuid.UUID, question_id: uuid.UUID) -> bool:
    """Resume the schedule where it left off."""
    states = PracticeStateRepository(session, user_id)
    states.hold_question(question_id)
    return states.set_removed_at(question_id, None)
