"""Grading a submitted attempt (T2.13, plan `t2.15-t2.13-t2.16-answer-grade.md`, "Giao dịch và
khóa"). The one place that writes a grade: the synchronous path, and the queue's
(`handlers.grade_completed`, T4.19), through `record_grade`.

The attempt is already submitted and committed (the answer is never lost to a failed grading).
Then, in the caller's transaction:

1. the attempt is this user's (404 otherwise), and its grading lock is free (else "in_progress");
2. a grade that exists is returned as it is: "Chấm lại" never pays the AI twice;
3. "Không nhớ" is graded by the system, without the AI (US-04 AC2);
4. otherwise the request is built and checked against ai-service's limits, the AI is asked, and
   its answer checked again in core (R03, R41 layer 2);
5. `record_grade` writes grade, grade_unit, review_log and memory_state together, or nothing.

When the AI cannot be reached or fails for a reason that may clear (T4.19), the request is
queued instead (`grade.requested.v1` through the outbox, the request a file): the answer is
"in progress", and the grade is written later by the handler of `grade.completed.v1`. A grading
already queued is not paid again by "Chấm lại".
"""

import json
import logging
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal, Protocol
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from core_api.clients.ai_client import Failure, Graded, NotGraded
from core_api.clients.storage import ObjectStorage, StorageUnavailableError
from core_api.db.models import Attempt, Grade, GradeJob, User
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
from core_api.domain.scheduling.multi_unit import current_rule, unit_ratings
from core_api.domain.scheduling.rating import Verdict
from core_api.domain.scheduling.replay import schedule_review
from core_api.messaging.envelope import GradeRequested
from core_api.messaging.outbox import enqueue_event
from core_api.repositories.grade_job import GradeJobRepository
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
# A queued grading that has not come back by then is lost (an event in the dead letter): the
# screen offers "Chấm lại" and asking again queues it anew (PR #49 review, 28/10).
QUEUED_GRADING_LIMIT = timedelta(hours=1)
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
    session: Session,
    user: User,
    attempt_id: uuid.UUID,
    grader: Grader,
    *,
    environment: str,
    may_call_ai: Callable[[], bool] = lambda: True,
    storage: ObjectStorage | None = None,
    now: datetime | None = None,
) -> GradingOutcome:
    """Grade a submitted attempt of `user`. AttemptNotFoundError when it is not theirs,
    AttemptNotSubmittedError while it is a draft. `may_call_ai` is asked just before paying the
    AI (the rate limit, plan 🟠4): it never stands between the user and a saved answer. With a
    `storage`, a grading that failed for a reason that may clear is queued (T4.19) instead."""
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
    job = GradeJobRepository(session, user.id).for_attempt(attempt_id)
    if job is not None and queued_in_progress(job, now or _now()):
        return GradingOutcome("in_progress")  # asked once; ai-service answers when it is back

    question = QuestionRepository(session, user.id).get(attempt.question_id)
    assert question is not None  # an attempt's question is never deleted (foreign key)
    unit_ins = units_of(session, user.id, question.id)

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
        if not may_call_ai():
            return _failed("unavailable", "rate_limited")
        answered = grader.grade(payload)
        if isinstance(answered, NotGraded):
            if answered.failure == "unavailable" and storage is not None:
                return _queued(session, user, attempt.id, payload, storage, now or _now())
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
        _log.error("grade not recorded", exc_info=error)
        return GradingOutcome("failed", "unavailable")
    return GradingOutcome("graded", grade=grade)


def units_of(session: Session, user_id: uuid.UUID, question_id: uuid.UUID) -> list[UnitIn]:
    """The units a question asks about, with their sources, in the order requests list them."""
    units = QuestionUnitRepository(session, user_id).units_of(question_id)
    anchors = AnchorRepository(session, user_id).of_units([unit.id for unit in units])
    return [
        UnitIn(
            unit.id,
            unit.title,
            [AnchorIn(a.id, a.quote_text) for a in anchors if a.unit_id == unit.id],
        )
        for unit in sorted(units, key=lambda unit: unit.id)
    ]


def _now() -> datetime:
    return datetime.now(UTC)


def queued_in_progress(job: GradeJob, now: datetime) -> bool:
    """A job still waiting for ai-service, and not for longer than `QUEUED_GRADING_LIMIT`."""
    return job.status == "queued" and now - job.updated_at <= QUEUED_GRADING_LIMIT


def _queued(
    session: Session,
    user: User,
    attempt_id: uuid.UUID,
    payload: Mapping[str, object],
    storage: ObjectStorage,
    now: datetime,
) -> GradingOutcome:
    """Send the request to ai-service through the queue (T4.19): the request is a file under the
    user's own prefix (claim-check: an answer never travels in an event), then the job and the
    event are written in the caller's transaction, so both exist or neither does."""
    key = f"users/{user.id}/grading/{attempt_id}/request-{uuid.uuid4()}.json"
    try:
        storage.write(key, json.dumps(payload).encode(), content_type="application/json")
    except StorageUnavailableError:
        _log.warning("grade request not stored")
        return GradingOutcome("failed", "unavailable")
    GradeJobRepository(session, user.id).queue(attempt_id, key, now)
    enqueue_event(
        session, GradeRequested(attempt_id=attempt_id, request_key=key), user_id=user.id, now=now
    )
    _log.info("grade queued", extra={"attempt_id": str(attempt_id)})
    return GradingOutcome("in_progress")


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
    ratings = unit_ratings(
        current_rule(),
        {unit_id: Verdict(checked.units[unit_id]) for unit_id in unit_ids},
        level=question.level,
    )
    for unit_id in unit_ids:
        rating = ratings[unit_id]
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
    """A grading core refuses: ERROR when the request or the answer is wrong (R41 layer 2, D-6),
    WARNING when only the rate limit stood in the way."""
    level = logging.ERROR if failure == "invalid" else logging.WARNING
    _log.log(level, "grade refused", extra={"outcome": reason})
    return GradingOutcome("failed", failure)
