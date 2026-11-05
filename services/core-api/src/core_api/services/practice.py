"""Record a graded practice attempt in the question's own FSRS schedule (T8.3, ADR-0029).

Practice never writes `review_log` or `memory_state`: the two schedules are independent.
The caller (the grading path, T8.4) commits and turns a "forgot" answer into `incorrect`.
"""

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from core_api.db.models import User
from core_api.domain.mastery import (
    DEFAULT_CONFIG,
    MasteryConfig,
    PracticeVerdict,
    rating_for,
)
from core_api.domain.scheduling.practice import PracticeState, verdict_of
from core_api.repositories.practice import PracticeLogRepository, PracticeStateRepository
from core_api.repositories.practice_removal import PracticeRemovalRepository
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
    config: MasteryConfig = DEFAULT_CONFIG,
) -> PracticeState:
    """One log row for the grade, then the question's state rebuilt from its log, in the caller's
    transaction. The first attempt creates the state; the same grade twice changes nothing.

    The state is always rebuilt, not stepped: a regrade of an older attempt or a grade that
    arrives late must give the same state a replay gives (US-06 AC7, US-16 AC10). The time of the
    review is the attempt's `submitted_at`, never the time of this call: a regrade made now must
    not move an old attempt in the history (as `overriding.py` does for cards)."""
    # The user row first, the lock `optimize_fsrs` takes, so a grade during the weekly fit waits
    # and rebuilds with the new parameters (T5.9c). NO KEY UPDATE, as `grading.record_grade`:
    # FOR UPDATE would deadlock with an exam PATCH.
    session.execute(
        select(User)
        .where(User.id == user_id)
        .with_for_update(key_share=True)
        .execution_options(populate_existing=True)  # the job may have committed new parameters
    ).all()
    states = PracticeStateRepository(session, user_id)
    log = PracticeLogRepository(session, user_id)
    states.hold_question(question_id)
    grade = GradeRepository(session, user_id).get(grade_id)
    attempt = AttemptRepository(session, user_id).get(grade.attempt_id) if grade else None
    if grade is None or attempt is None or attempt.question_id != question_id:
        raise GradeMismatchError(grade_id)
    assert attempt.submitted_at is not None  # a grade exists only for a submitted attempt
    at = attempt.submitted_at
    if log.by_grade(grade_id) is None:
        # "Previous" is the last counted attempt of an earlier learning day: a same-day try is
        # replaced by this one (QA2-FSRS), so it cannot unlock Easy.
        day_of = log.day_of()
        today = day_of(at)
        earlier = [
            r
            for r in log.effective([question_id])
            if r.attempt_id != grade.attempt_id and day_of(r.reviewed_at) < today
        ]
        previous = verdict_of(earlier[-1].rating) if earlier else None
        rating = rating_for(verdict, active_seconds, reference_seconds, previous, timing_ok, config)
        log.append(question_id, rating=rating, reviewed_at=at, grade_id=grade_id)
        states.rebuild([question_id])
    state = states.state(question_id)
    assert state is not None
    return state


def remove(
    session: Session,
    user_id: uuid.UUID,
    question_id: uuid.UUID,
    at: datetime,
    *,
    command_id: uuid.UUID | None = None,
) -> bool:
    """Take the question out of practice: one `removed` event in the append-only log (the truth,
    kept for a question never attempted too), then the schedule's cache. The question's row is
    locked before the event is written. False for a question never attempted: it has no state."""
    states = PracticeStateRepository(session, user_id)
    states.hold_question(question_id)
    removals = PracticeRemovalRepository(session, user_id)
    if removals.in_practice(question_id):
        removals.append(question_id, "removed", at=at, command_id=command_id)
    return states.set_removed_at(question_id, at)


def readd(
    session: Session,
    user_id: uuid.UUID,
    question_id: uuid.UUID,
    *,
    at: datetime | None = None,
    command_id: uuid.UUID | None = None,
) -> bool:
    """Put the question back: a `readded` event, and the schedule resumes where it left off."""
    states = PracticeStateRepository(session, user_id)
    states.hold_question(question_id)
    removals = PracticeRemovalRepository(session, user_id)
    if not removals.in_practice(question_id):
        removals.append(question_id, "readded", at=at, command_id=command_id)
    return states.set_removed_at(question_id, None)
