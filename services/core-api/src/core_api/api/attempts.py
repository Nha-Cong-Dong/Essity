"""One attempt (T2.13, US-04, US-05; plan `t2.15-t2.13-t2.16-answer-grade.md`): submitting it grades
it at once, "Chấm lại" grades it again when grading failed, and reading it back gives the screen
its state. Saving a draft stays with the review session API (T2.9).

Submitting is two transactions. The first saves and submits the answer and commits: whatever
grading does next, the answer is kept (PLAN T2.13). The second grades it (`core_api.grading`).
A grading that fails answers 200 with `grading: "failed"`: the answer is saved, and the screen
offers "Chấm lại" (PLAN T2.13 23/10)."""

import datetime as dt
import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from core_api.api.deps import Now, VerifiedUser, verified_user
from core_api.api.ping import get_ai_client
from core_api.api.review_sessions import AnswerIn
from core_api.clients.ai_client import AiServiceClient, Failure
from core_api.config import get_settings
from core_api.db.models import Attempt, Grade
from core_api.db.session import DbSession
from core_api.grading import GradingOutcome, grade_attempt
from core_api.repositories.question import QuestionRepository, QuestionUnitRepository
from core_api.repositories.review import (
    AttemptNotDraftError,
    AttemptNotFoundError,
    AttemptNotSubmittedError,
    AttemptRepository,
    GradeRepository,
    ReviewSessionEndedError,
)
from core_api.repositories.unit import AnchorRepository
from core_api.security.rate_limit import (
    RateLimit,
    RateLimitedError,
    RateLimiter,
    RateLimiterUnavailableError,
    get_rate_limiter,
)

router = APIRouter(prefix="/v1", dependencies=[Depends(verified_user)])

# Each grading is a paid AI call (plan D-12; T2.11, the monthly cap, comes later).
GRADINGS_PER_USER = RateLimit("grade_user", 20, dt.timedelta(minutes=1))

Grader = Annotated[AiServiceClient, Depends(get_ai_client)]
Limiter = Annotated[RateLimiter, Depends(get_rate_limiter)]


class UnitResult(BaseModel):
    unit_id: uuid.UUID
    title: str
    verdict: Literal["correct", "partial", "incorrect"]


class Source(BaseModel):
    anchor_id: uuid.UUID
    quote_text: str
    kind: str  # "document" or "notes" (anchor.source)
    page_no: int | None


class ResultOut(BaseModel):
    overall: Literal["correct", "partial", "incorrect", "forgot"]
    understanding: int | None
    missing: list[str]
    units: list[UnitResult]
    reference_answer: str
    sources: list[Source]
    practice: bool  # the fake grader's: the screen says "Chấm thử"


class QuestionRef(BaseModel):
    prompt: str


class AttemptView(BaseModel):
    status: Literal["draft", "submitted"]
    grading: Literal["graded", "failed", "in_progress"] | None
    failure: Failure | None
    result: ResultOut | None
    answer_text: str | None
    submitted_at: dt.datetime | None
    question: QuestionRef | None


def _error(code: int, detail: str) -> HTTPException:
    return HTTPException(status_code=code, detail=detail)


def result_of(session: DbSession, user_id: uuid.UUID, attempt: Attempt, grade: Grade) -> ResultOut:
    """What the result screen shows of a grade (US-05 AC2): the verdicts by unit, the reference
    answer and the sources the grade used. "Không nhớ" shows every source of the question."""
    question = QuestionRepository(session, user_id).get(attempt.question_id)
    assert question is not None
    units = {u.id: u for u in QuestionUnitRepository(session, user_id).units_of(question.id)}
    anchors = AnchorRepository(session, user_id).of_units(list(units))
    if grade.overall == "forgot":
        used = anchors
    else:
        ids = [uuid.UUID(str(a)) for a in grade.anchors_used]
        by_id = {a.id: a for a in anchors}
        used = [by_id[a] for a in ids if a in by_id]
    verdicts = GradeRepository(session, user_id).unit_verdicts(grade.id)
    return ResultOut(
        overall=grade.overall,  # type: ignore[arg-type]
        understanding=grade.understanding,
        missing=list(grade.missing),
        units=[
            UnitResult(unit_id=unit_id, title=units[unit_id].title, verdict=verdict)  # type: ignore[arg-type]
            for unit_id, verdict in sorted(verdicts.items(), key=lambda item: units[item[0]].title)
        ],
        reference_answer=question.reference_answer,
        sources=[
            Source(anchor_id=a.id, quote_text=a.quote_text, kind=a.source, page_no=a.page_no)
            for a in used
        ],
        practice=grade.source == "fake",
    )


def attempt_view(
    session: DbSession, user_id: uuid.UUID, attempt: Attempt, outcome: GradingOutcome | None
) -> AttemptView:
    question = QuestionRepository(session, user_id).get(attempt.question_id)
    if attempt.status != "submitted":
        # Plan 🟠3, US-04 AC1: a draft says nothing of the answer it is checked against.
        return AttemptView(
            status="draft",
            grading=None,
            failure=None,
            result=None,
            answer_text=attempt.answer_text,
            submitted_at=None,
            question=QuestionRef(prompt=question.prompt) if question else None,
        )
    if outcome is None:
        grades = GradeRepository(session, user_id)
        grade = grades.latest_for_attempt(attempt.id)
        if grade is not None:
            outcome = GradingOutcome("graded", grade=grade)
        elif grades.is_being_graded(attempt.id):
            outcome = GradingOutcome("in_progress")
        else:
            outcome = GradingOutcome("failed")
    result = None
    if outcome.grading == "graded" and outcome.grade is not None:
        result = result_of(session, user_id, attempt, outcome.grade)
    return AttemptView(
        status="submitted",
        grading=outcome.grading,
        failure=outcome.failure,
        result=result,
        answer_text=attempt.answer_text,
        submitted_at=attempt.submitted_at,
        question=QuestionRef(prompt=question.prompt) if question else None,
    )


@router.post("/attempts/{attempt_id}/submit")
def submit_attempt(
    attempt_id: uuid.UUID,
    body: AnswerIn,
    user: VerifiedUser,
    session: DbSession,
    now: Now,
    grader: Grader,
    limiter: Limiter,
) -> AttemptView:
    """Save the last text and submit (nothing typed after the last draft save is lost), commit,
    then grade. Submitting again, or from a second tab, grades what was submitted first."""
    attempts = AttemptRepository(session, user.id)
    found = attempts.get(attempt_id)
    if found is None:
        raise _error(status.HTTP_404_NOT_FOUND, "attempt_not_found")
    if found.status != "submitted":
        if not body.dont_remember and not body.answer_text.strip():
            raise _error(status.HTTP_422_UNPROCESSABLE_CONTENT, "answer_empty")
        try:
            attempts.save_draft(
                attempt_id, answer_text=body.answer_text, dont_remember=body.dont_remember
            )
            attempts.submit(attempt_id, now)
        except ReviewSessionEndedError as error:
            raise _error(status.HTTP_409_CONFLICT, "session_ended") from error
        except AttemptNotDraftError:
            session.rollback()  # another request submitted it first: grade that one
    session.commit()  # the answer is kept, whatever grading does next
    return _graded_view(session, user, attempt_id, grader, limiter)


@router.post("/attempts/{attempt_id}/regrade")
def regrade_attempt(
    attempt_id: uuid.UUID, user: VerifiedUser, session: DbSession, grader: Grader, limiter: Limiter
) -> AttemptView:
    """ "Chấm lại": grade a submitted answer that has no grade yet; a graded one is returned as it
    is, never paid for twice."""
    return _graded_view(session, user, attempt_id, grader, limiter)


@router.get("/attempts/{attempt_id}")
def read_attempt(attempt_id: uuid.UUID, user: VerifiedUser, session: DbSession) -> AttemptView:
    """The attempt as the answer and result screens show it (after a reload too). Never grades."""
    found = AttemptRepository(session, user.id).get(attempt_id)
    if found is None:
        raise _error(status.HTTP_404_NOT_FOUND, "attempt_not_found")
    return attempt_view(session, user.id, found, None)


def _graded_view(
    session: DbSession, user: VerifiedUser, attempt_id: uuid.UUID, grader: Grader, limiter: Limiter
) -> AttemptView:
    def may_call_ai() -> bool:
        try:
            limiter.enforce(GRADINGS_PER_USER, str(user.id))
        except (RateLimitedError, RateLimiterUnavailableError):
            return False
        return True

    try:
        outcome = grade_attempt(
            session,
            user,
            attempt_id,
            grader,
            environment=get_settings().environment,
            may_call_ai=may_call_ai,
        )
    except AttemptNotFoundError as error:
        raise _error(status.HTTP_404_NOT_FOUND, "attempt_not_found") from error
    except AttemptNotSubmittedError as error:
        raise _error(status.HTTP_409_CONFLICT, "attempt_not_submitted") from error
    found = AttemptRepository(session, user.id).get(attempt_id)
    assert found is not None
    return attempt_view(session, user.id, found, outcome)
