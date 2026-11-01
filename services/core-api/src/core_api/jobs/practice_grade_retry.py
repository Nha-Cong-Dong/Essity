"""The `practice_grade_retry` job (T8.4b, US-05 AC14): practice answers saved while the AI had no
turn (or was down) sit in `grade_job` with an empty `request_key`; this job grades them when
there is a turn again, through the same `grade_practice_attempt` a "Chấm lại" uses, so a grade and
its schedule step are written once
whoever gets there first (the attempt's grading lock).

Every run looks at the oldest-touched `BATCH` rows, one transaction each:

- a row another request holds (row lock or grading lock) is skipped, not waited for;
- a row older than `MAX_AGE`, or whose user, subject or question is gone (account deleted, subject
  deleted, question marked worthless), ends as `failed` without a call to the AI (ADR-0001/0007);
- a user over the per-user grading limit is left for the next run; the other users go on;
- the AI having no turn (budget, down, switched off) stops the whole run: no call per row;
- a row that raises is rolled back, logged by id and exception type, and pushed to the back of the
  queue (`updated_at`), so one poison row never starves the others.

Logs hold ids and counts, never the answer or an exception message (ADR-0013). Running twice is
harmless.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from core_api.api.attempts import GRADINGS_PER_USER
from core_api.clients.ai_client import AiServiceClient
from core_api.clients.redis import get_redis
from core_api.config import get_settings
from core_api.db.engine import get_engine
from core_api.db.models import Attempt, GradeJob, User
from core_api.jobs.handler import periodic_job
from core_api.repositories.grade_job import GradeJobRepository
from core_api.repositories.practice_attempt import PracticeAttemptRepository
from core_api.repositories.question import QuestionRepository
from core_api.repositories.subject import SubjectRepository
from core_api.security.rate_limit import (
    RateLimit,
    RateLimitedError,
    RateLimiter,
    RateLimiterUnavailableError,
)
from core_api.services.practice_grading import PracticeAi, grade_practice_attempt

PRACTICE_GRADE_RETRY = "practice_grade_retry"
BATCH = 20
# A grading that has waited this long is given up: the screen offers "Chấm lại".
MAX_AGE = timedelta(days=7)

_log = logging.getLogger("core_api.jobs")


class Limiter(Protocol):
    """What the job needs of `RateLimiter` (a fake in tests)."""

    def enforce(self, rule: RateLimit, key: str) -> None: ...


@dataclass
class RetryReport:
    graded: int = 0
    failed: int = 0
    skipped: int = 0
    halted: bool = False


def _due(session: Session, batch: int) -> list[tuple[uuid.UUID, uuid.UUID, uuid.UUID]]:
    rows = session.execute(
        select(GradeJob.id, GradeJob.user_id, GradeJob.attempt_id)
        .join(Attempt, (Attempt.id == GradeJob.attempt_id) & (Attempt.user_id == GradeJob.user_id))
        .where(
            GradeJob.status == "queued",
            GradeJob.request_key == "",
            Attempt.review_session_id.is_(None),
            Attempt.status == "submitted",
        )
        .order_by(GradeJob.updated_at)
        .limit(batch)
    ).all()
    return [(row[0], row[1], row[2]) for row in rows]


def _live(session: Session, user_id: uuid.UUID, attempt_id: uuid.UUID) -> bool:
    """Whether the answer may still be graded: the account, the subject and the question are
    all still there, and the attempt is a submitted practice one of this user."""
    user = session.get(User, user_id)
    if user is None or user.deleted_at is not None:
        return False
    attempt = PracticeAttemptRepository(session, user_id).get_practice(attempt_id)
    if attempt is None or attempt.status != "submitted":
        return False
    question = QuestionRepository(session, user_id).get(attempt.question_id)
    if question is None or question.status != "active":
        return False
    return SubjectRepository(session, user_id).get(question.subject_id) is not None


Step = str  # "graded" | "failed" | "skipped" | "limited" | "halt"


def _retry_one(
    session: Session,
    ai: PracticeAi,
    limiter: Limiter,
    job_id: uuid.UUID,
    user_id: uuid.UUID,
    now: datetime,
) -> Step:
    # Read again under the row lock: the API may have settled the row since `_due` looked.
    job = session.scalars(
        select(GradeJob)
        .where(GradeJob.id == job_id, GradeJob.status == "queued", GradeJob.request_key == "")
        .with_for_update(skip_locked=True)
    ).one_or_none()
    if job is None:
        session.rollback()
        return "skipped"
    attempt_id = job.attempt_id
    jobs = GradeJobRepository(session, user_id)
    if now - job.created_at > MAX_AGE:
        jobs.fail(attempt_id, "unavailable", now)
        session.commit()
        return "failed"
    if not _live(session, user_id, attempt_id):
        jobs.fail(attempt_id, "invalid", now)
        session.commit()
        return "failed"
    limited: list[bool] = []

    def may_call() -> bool:
        try:
            limiter.enforce(GRADINGS_PER_USER, str(user_id))
        except (RateLimitedError, RateLimiterUnavailableError):
            limited.append(True)
            return False
        return True

    outcome = grade_practice_attempt(session, user_id, attempt_id, ai, may_call_ai=may_call)
    step: Step
    if outcome.grading == "in_progress":
        step = "skipped"
    elif outcome.grading == "graded":
        jobs.settle_practice(attempt_id, "graded", None, now)
        step = "graded"
    elif outcome.grading == "failed" and outcome.failure != "disabled":
        jobs.settle_practice(attempt_id, "failed", outcome.failure, now)
        step = "failed"
    else:  # pending, or the AI is switched off: stays queued, at the back of the line
        jobs.settle_practice(attempt_id, "pending", None, now)
        step = "limited" if limited else "halt"
    session.commit()
    return step


def retry_pending(
    session: Session,
    ai: PracticeAi,
    limiter: Limiter,
    now: datetime,
    *,
    batch: int = BATCH,
) -> RetryReport:
    """Grade up to `batch` queued practice answers; see the module docstring."""
    report = RetryReport()
    limited: set[uuid.UUID] = set()
    for job_id, user_id, attempt_id in _due(session, batch):
        if user_id in limited:
            report.skipped += 1
            continue
        try:
            step = _retry_one(session, ai, limiter, job_id, user_id, now)
        except Exception as error:  # noqa: BLE001 - one bad row must not stop the queue
            session.rollback()
            _log.error(
                "practice grade retry failed",
                extra={"attempt_id": str(attempt_id), "error_type": type(error).__name__},
            )
            _push_back(session, user_id, attempt_id, now)
            report.skipped += 1
            continue
        if step == "graded":
            report.graded += 1
        elif step == "failed":
            report.failed += 1
        elif step == "limited":
            limited.add(user_id)
            report.skipped += 1
        elif step == "halt":
            report.halted = True
            break
        else:
            report.skipped += 1
    return report


def _push_back(session: Session, user_id: uuid.UUID, attempt_id: uuid.UUID, now: datetime) -> None:
    """Best effort: the row that failed goes behind the others for the next run."""
    try:
        GradeJobRepository(session, user_id).settle_practice(attempt_id, "pending", None, now)
        session.commit()
    except Exception:  # noqa: BLE001
        session.rollback()


@periodic_job(PRACTICE_GRADE_RETRY, cron="*/10 * * * *")
def practice_grade_retry_job(payload: dict[str, Any]) -> None:
    settings = get_settings()
    ai = AiServiceClient.from_settings(settings)
    try:
        with Session(get_engine()) as session:
            report = retry_pending(session, ai, RateLimiter(get_redis()), datetime.now(UTC))
    finally:
        ai.close()
    _log.info(
        "practice grade retry",
        extra={
            "graded_count": report.graded,
            "failed_count": report.failed,
            "skipped_count": report.skipped,
            "halted": report.halted,
        },
    )
