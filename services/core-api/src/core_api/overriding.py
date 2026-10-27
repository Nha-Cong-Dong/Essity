"""Writing an override (T2.18, US-09 AC2, AC3), in the caller's transaction. Like grading
(`grading.py`) it adds a grade, one review_log row per unit, and rebuilds the schedule of those
units from review_log: the same replay as from scratch (T2.6), so the result cannot differ from
it. The machine's grade stays (layer 3 is append-only).

The attempt's grading lock is taken first, so an override never runs beside a grading or another
override of the same attempt."""

import uuid

from sqlalchemy.orm import Session

from core_api.db.models import Grade, User
from core_api.domain.override import Choice, override_of
from core_api.domain.scheduling.rating import rating_for
from core_api.repositories.question import QuestionRepository
from core_api.repositories.review import (
    AttemptRepository,
    GradeRepository,
    MemoryStateRepository,
    ReviewLogRepository,
)
from core_api.repositories.subject import SubjectNotFoundError, SubjectRepository
from core_api.repositories.unit import KnowledgeUnitRepository


class GradeNotFoundError(LookupError):
    """No such grade for this user."""


class GradeNotCurrentError(ValueError):
    """The grade is not the attempt's newest: a newer one stands (US-09)."""


class GradeBusyError(ValueError):
    """The attempt is being graded or overridden by another request."""


def override_grade(session: Session, user: User, grade_id: uuid.UUID, choice: Choice) -> Grade:
    """The attempt's grade after the user's verdict: a new `user_override` grade, or the current
    one when it already says so. GradeNotFoundError (not this user's, or not there),
    GradeNotCurrentError, GradeBusyError, SubjectNotFoundError (the subject was deleted)."""
    grades = GradeRepository(session, user.id)
    grade = grades.get(grade_id)
    if grade is None:
        raise GradeNotFoundError(grade_id)
    if not grades.try_lock_attempt(grade.attempt_id):
        raise GradeBusyError(grade.attempt_id)
    current = grades.latest_for_attempt(grade.attempt_id)
    assert current is not None
    if current.overall == choice and (current.id == grade.id or current.source == "user_override"):
        return current  # already what the user says: a second tap changes nothing
    if current.id != grade.id:
        raise GradeNotCurrentError(grade_id)

    attempt = AttemptRepository(session, user.id).get(grade.attempt_id)
    assert attempt is not None and attempt.submitted_at is not None
    question = QuestionRepository(session, user.id).get(attempt.question_id)
    assert question is not None
    subjects = SubjectRepository(session, user.id)
    subjects.hold_for_share(question.subject_id)  # as grading does: a moved exam goes first
    if subjects.get(question.subject_id) is None:
        raise SubjectNotFoundError(question.subject_id)
    unit_ids = sorted(grades.unit_verdicts(current.id))
    KnowledgeUnitRepository(session, user.id).lock(unit_ids)

    made = override_of(choice, unit_ids)
    new = grades.add_with_units(
        attempt.id,
        source="user_override",
        overall=made.overall,
        understanding=made.understanding,
        units=made.units,
        run_id=None,
        anchors_used=[str(anchor) for anchor in current.anchors_used],
    )
    logs = ReviewLogRepository(session, user.id)
    for unit_id in unit_ids:
        logs.append(
            unit_id,
            rating=rating_for(made.units[unit_id]),
            reviewed_at=attempt.submitted_at,
            grade_id=new.id,
        )
    MemoryStateRepository(session, user.id).rebuild(
        subject_id=question.subject_id, unit_ids=unit_ids
    )
    return new
