"""Grading a submitted attempt (T2.13, plan `t2.15-t2.13-t2.16-answer-grade.md`, "Giao dịch và
khóa"). The one place that writes a grade: the synchronous path now, the queue (T4.19) later.

The attempt is already submitted and committed (the answer is never lost to a failed grading).
Then, in the caller's transaction:

1. the attempt is this user's (404 otherwise), and its grading lock is free (else "in_progress");
2. a grade that exists is returned as it is: "Chấm lại" never pays the AI twice;
3. "Không nhớ" is graded by the system, without the AI (US-04 AC2);
4. otherwise the request is built and checked against ai-service's limits, the AI is asked, and
   its answer checked again in core (R03, R41 layer 2);
5. `record_grade` writes grade, grade_unit, review_log and memory_state together, or nothing.
"""

import logging
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, Protocol
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from core_api.clients.ai_client import Failure, Graded, NotGraded
from core_api.db.models import Attempt, Grade, User
from core_api.domain.grading import (
    AnchorIn,
    CheckedGrade,
    QuestionIn,
    RequestRefused,
    ResponseRefused,
    UnitIn,
    build_request,
    check_response,
)
from core_api.domain.scheduling.rating import Verdict, rating_for
from core_api.domain.scheduling.replay import schedule_review
from core_api.repositories.question import QuestionRepository, QuestionUnitRepository
from core_api.repositories.review import (
    AttemptNotFoundError,
    AttemptNotSubmittedError,
    AttemptRepository,
    GradeRepository,
    MemoryStateRepository,
    ReviewLogRepository,
    UnitsMismatchError,
)
from core_api.repositories.subject import SubjectNotFoundError, SubjectRepository
from core_api.repositories.unit import AnchorRepository, KnowledgeUnitRepository

_log = logging.getLogger(__name__)
Grading = Literal["graded", "failed", "in_progress"]


class Grader(Protocol):
    """What grading needs of ai-service (AiServiceClient, or a stub in tests)."""

    def grade(self, payload: Mapping[str, object]) -> Graded | NotGraded: ...


@dataclass(frozen=True)
class GradingOutcome:
    grading: Grading
    failure: Failure | None = None
    grade: Grade | None = None


def grade_attempt(
    session: Session, user: User, attempt_id: uuid.UUID, grader: Grader, *, environment: str
) -> GradingOutcome:
    """Grade a submitted attempt of `user`. AttemptNotFoundError when it is not theirs,
    AttemptNotSubmittedError while it is a draft."""
    attempt = AttemptRepository(session, user.id).get(attempt_id)
    if attempt is None:
        raise AttemptNotFoundError(attempt_id)
    if attempt.status != "submitted":
        raise AttemptNotSubmittedError(attempt_id)
    grades = GradeRepository(session, user.id)
    if not grades.try_lock_attempt(attempt_id):
        return GradingOutcome("in_progress")
    existing = grades.latest_for_attempt(attempt_id)
    if existing is not None:
        return GradingOutcome("graded", grade=existing)

    question = QuestionRepository(session, user.id).get(attempt.question_id)
    assert question is not None  # an attempt's question is never deleted (foreign key)
    units = QuestionUnitRepository(session, user.id).units_of(question.id)
    anchors = AnchorRepository(session, user.id).of_units([unit.id for unit in units])
    unit_ins = [
        UnitIn(
            unit.id,
            unit.title,
            [AnchorIn(a.id, a.quote_text) for a in anchors if a.unit_id == unit.id],
        )
        for unit in sorted(units, key=lambda unit: unit.id)
    ]

    if attempt.dont_remember:
        checked = CheckedGrade(
            source="system",
            overall="forgot",
            understanding=None,
            missing=[],
            units={unit.unit_id: "incorrect" for unit in unit_ins},
            anchors_used=[],
            run_id=None,
        )
    else:
        try:
            payload = build_request(
                user_id=user.id,
                subject_id=question.subject_id,
                attempt_id=attempt.id,
                question=QuestionIn(question.prompt, question.rubric, question.reference_answer),
                answer=attempt.answer_text,
                units=unit_ins,
            )
        except RequestRefused as refused:
            return _failed("invalid", f"request_{refused}")
        answered = grader.grade(payload)
        if isinstance(answered, NotGraded):
            return GradingOutcome("failed", answered.failure)
        try:
            checked = check_response(answered.response, units=unit_ins, environment=environment)
        except ResponseRefused as refused:
            return _failed("invalid", f"response_{refused}")

    try:
        with session.begin_nested():
            grade = record_grade(session, user, attempt, checked)
    except (UnitsMismatchError, SubjectNotFoundError):
        return _failed("invalid", "units_changed")
    except Exception as error:  # noqa: BLE001 - rolled back above; the answer stays submitted
        _log.error("grade not recorded", extra={"error_type": type(error).__name__})
        return GradingOutcome("failed", "unavailable")
    return GradingOutcome("graded", grade=grade)


def record_grade(session: Session, user: User, attempt: Attempt, checked: CheckedGrade) -> Grade:
    """Write a grade and the schedule it moves, in the caller's transaction (T2.13 steps 5–7).
    Locks: the subject FOR SHARE (a moved exam replays first, or waits for this), then the units
    by id. A review older than the unit's last one replays the unit (PLAN T2.13 25/10)."""
    question = QuestionRepository(session, user.id).get(attempt.question_id)
    assert question is not None and attempt.submitted_at is not None
    subjects = SubjectRepository(session, user.id)
    subjects.hold_for_share(question.subject_id)
    found = subjects.get_with_exam(question.subject_id)
    if found is None:
        raise SubjectNotFoundError(question.subject_id)
    exam_day = found[1].exam_date
    unit_ids = sorted(checked.units)
    KnowledgeUnitRepository(session, user.id).lock(unit_ids)

    grade = GradeRepository(session, user.id).add_with_units(
        attempt.id,
        source=checked.source,
        overall=Verdict(checked.overall),
        understanding=checked.understanding,
        units={unit: Verdict(verdict) for unit, verdict in checked.units.items()},
        run_id=checked.run_id,
        missing=checked.missing,
        anchors_used=[str(anchor) for anchor in checked.anchors_used],
    )
    logs = ReviewLogRepository(session, user.id)
    states = MemoryStateRepository(session, user.id)
    tz = ZoneInfo(user.timezone)
    reviewed_at = attempt.submitted_at
    late: list[uuid.UUID] = []
    for unit_id in unit_ids:
        rating = rating_for(Verdict(checked.units[unit_id]))
        logs.append(unit_id, rating=rating, reviewed_at=reviewed_at, grade_id=grade.id)
        state = states.state(unit_id)
        if state is not None and reviewed_at < state.last_review:
            late.append(unit_id)
            continue
        states.upsert(
            unit_id,
            "core",
            schedule_review(
                state,
                rating,
                reviewed_at,
                exam_day=exam_day,
                tz=tz,
                day_start_hour=user.day_start_hour,
            ),
        )
    if late:
        states.rebuild(subject_id=question.subject_id, unit_ids=late)
    session.flush()
    return grade


def _failed(failure: Failure, reason: str) -> GradingOutcome:
    _log.warning("grade refused", extra={"outcome": reason})
    return GradingOutcome("failed", failure)
