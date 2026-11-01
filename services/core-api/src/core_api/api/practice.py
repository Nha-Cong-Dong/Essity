"""Practice questions: open one, answer it, grade it (T8.4, US-05 AC9-AC14, US-16 AC5/AC10).

A practice attempt belongs to no review session, so these routes are the only way to reach it: the
review routes answer 404 for it. Submitting is two transactions: the first saves the answer and
its timing and commits (whatever grading does next, the answer is kept); the second grades it
(`services.practice_grading`). When the AI is out of turns or down the answer is 200 with
`grading: "pending"` and the screen says it will be graded when there is a turn.

The reference answer and the rubric are never sent to a draft: the view shows them only once the
attempt is submitted (US-04 AC1). The server writes `served_at` when the question is first opened;
the client sends only `hidden_ms`.
"""

import datetime as dt
import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field

from core_api.api.attempts import GRADINGS_PER_USER, Limiter
from core_api.api.deps import Now, VerifiedUser, verified_user
from core_api.api.ping import get_ai_client
from core_api.api.review_sessions import AnswerText
from core_api.clients.ai_client import AiServiceClient
from core_api.db.models import Attempt, Grade, Question
from core_api.db.session import DbSession
from core_api.repositories.grade_job import GradeJobRepository
from core_api.repositories.practice_attempt import (
    AttemptNotDraftError,
    AttemptNotFoundError,
    DraftContendedError,
    PracticeAttemptRepository,
)
from core_api.repositories.question import QuestionNotFoundError, QuestionRepository
from core_api.repositories.review import GradeRepository
from core_api.repositories.subject import SubjectNotFoundError, SubjectRepository
from core_api.security.rate_limit import RateLimitedError, RateLimiterUnavailableError
from core_api.services.practice import remove
from core_api.services.practice_grading import (
    MAX_ANSWER_CHARS,
    GradeBusyError,
    GradeNotCurrentError,
    GradeNotFoundError,
    PracticeOutcome,
    ensure_reference,
    grade_practice_attempt,
    override_practice_grade,
    reference_time,
    rubric_of,
    standard_answer,
)

router = APIRouter(prefix="/v1/practice", dependencies=[Depends(verified_user)])

Ai = Annotated[AiServiceClient, Depends(get_ai_client)]
MAX_HIDDEN_MS = 24 * 3600 * 1000


class DraftIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    answer_text: AnswerText
    dont_remember: bool = False


class SubmitIn(DraftIn):
    # The tab's hidden time; never trusted (clamped in `practice_timing`). `served_at` is not here.
    hidden_ms: Annotated[int, Field(ge=0, le=MAX_HIDDEN_MS * 30)] = 0


class PracticeOverrideIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    verdict: Literal["correct", "incorrect"]


class QuestionRef(BaseModel):
    id: uuid.UUID
    prompt: str


class PracticeResultOut(BaseModel):
    grade_id: uuid.UUID  # what "Chấm sai" overrides
    overall: Literal["correct", "partial", "incorrect", "forgot"]
    missing: list[str]  # the rubric ideas not fully met
    reference_answer: str | None
    answer_origin: Literal["bank", "ai", "user"] | None  # "ai": the screen labels it
    differs_from_card_id: uuid.UUID | None = None  # "đáp án này khác thẻ X" when core knows it


class PracticeView(BaseModel):
    attempt_id: uuid.UUID
    status: Literal["draft", "submitted"]
    grading: Literal["graded", "pending", "failed", "in_progress"] | None
    failure: str | None
    result: PracticeResultOut | None
    answer_text: str | None
    dont_remember: bool
    submitted_at: dt.datetime | None
    timing_ok: bool | None
    question: QuestionRef


def _error(code: int, detail: str) -> HTTPException:
    return HTTPException(status_code=code, detail=detail)


def _view(
    session: DbSession,
    user_id: uuid.UUID,
    attempt: Attempt,
    question: Question,
    outcome: PracticeOutcome | None = None,
) -> PracticeView:
    ref = QuestionRef(id=question.id, prompt=question.prompt)
    if attempt.status != "submitted":
        return PracticeView(
            attempt_id=attempt.id,
            status="draft",
            grading=None,
            failure=None,
            result=None,
            answer_text=attempt.answer_text,
            dont_remember=attempt.dont_remember,
            submitted_at=None,
            timing_ok=None,
            question=ref,
        )
    if outcome is None:
        grades = GradeRepository(session, user_id)
        current = grades.latest_for_attempt(attempt.id)
        if current is not None:
            outcome = PracticeOutcome("graded", current)
        elif grades.is_being_graded(attempt.id):
            outcome = PracticeOutcome("in_progress")
        else:
            job = GradeJobRepository(session, user_id).for_attempt(attempt.id)
            if job is not None and job.status == "queued":
                outcome = PracticeOutcome("pending")  # saved, queued: graded when there is a turn
            else:  # failed for good, or an old answer nothing queued: "Chấm lại"
                outcome = PracticeOutcome("failed", failure=job.failure if job else "invalid")
    result = _result(question, outcome.grade) if outcome.grade is not None else None
    return PracticeView(
        attempt_id=attempt.id,
        status="submitted",
        grading=outcome.grading,
        failure=outcome.failure,
        result=result,
        answer_text=attempt.answer_text,
        dont_remember=attempt.dont_remember,
        submitted_at=attempt.submitted_at,
        timing_ok=attempt.timing_ok,
        question=ref,
    )


def _result(question: Question, grade: Grade) -> PracticeResultOut:
    return PracticeResultOut(
        grade_id=grade.id,
        overall=grade.overall,  # type: ignore[arg-type]
        missing=[str(m) for m in grade.missing],
        reference_answer=standard_answer(question),
        answer_origin=question.answer_origin,  # type: ignore[arg-type]
    )


def _owned(
    session: DbSession, user_id: uuid.UUID, attempt_id: uuid.UUID
) -> tuple[Attempt, Question]:
    attempt = PracticeAttemptRepository(session, user_id).get_practice(attempt_id)
    question = QuestionRepository(session, user_id).get(attempt.question_id) if attempt else None
    if attempt is None or question is None:
        raise _error(status.HTTP_404_NOT_FOUND, "attempt_not_found")
    return attempt, question


@router.post("/questions/{question_id}/open")
def open_question(
    question_id: uuid.UUID,
    user: VerifiedUser,
    session: DbSession,
    now: Now,
    ai: Ai,
    limiter: Limiter,
) -> PracticeView:
    """Serve a question: its open draft (made if there is none, with the server's `served_at`).
    A bank question with no answer gets an AI-drafted one now, once, so it is ready (AC13)."""
    attempts = PracticeAttemptRepository(session, user.id)
    try:
        attempt, _ = attempts.open_draft(question_id, now)
    except (QuestionNotFoundError, SubjectNotFoundError) as error:
        raise _error(status.HTTP_404_NOT_FOUND, "question_not_found") from error
    except DraftContendedError as error:
        raise _error(status.HTTP_409_CONFLICT, "try_again") from error
    session.commit()
    question = QuestionRepository(session, user.id).get(question_id)
    assert question is not None
    if standard_answer(question) is None and _may_call(limiter, user.id):
        ensure_reference(session, user.id, question, ai)
        session.commit()
    return _view(session, user.id, attempt, question)


@router.put("/attempts/{attempt_id}/draft", status_code=status.HTTP_204_NO_CONTENT)
def save_draft(
    attempt_id: uuid.UUID, body: DraftIn, user: VerifiedUser, session: DbSession
) -> Response:
    try:
        PracticeAttemptRepository(session, user.id).save_draft(
            attempt_id, answer_text=body.answer_text, dont_remember=body.dont_remember
        )
    except AttemptNotFoundError as error:
        raise _error(status.HTTP_404_NOT_FOUND, "attempt_not_found") from error
    except AttemptNotDraftError as error:
        raise _error(status.HTTP_409_CONFLICT, "attempt_not_draft") from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/attempts/{attempt_id}")
def read_attempt(attempt_id: uuid.UUID, user: VerifiedUser, session: DbSession) -> PracticeView:
    """The attempt as the screen shows it (after a reload too). Never grades."""
    attempt, question = _owned(session, user.id, attempt_id)
    return _view(session, user.id, attempt, question)


@router.post("/attempts/{attempt_id}/submit")
def submit_attempt(
    attempt_id: uuid.UUID,
    body: SubmitIn,
    user: VerifiedUser,
    session: DbSession,
    now: Now,
    ai: Ai,
    limiter: Limiter,
) -> PracticeView:
    """Save the last text, submit with the timing, commit; then grade. Submitting again, or from
    a second tab, grades what was submitted first and keeps its timing."""
    attempt, question = _owned(session, user.id, attempt_id)
    if attempt.status != "submitted":
        if not body.dont_remember and not body.answer_text.strip():
            raise _error(status.HTTP_422_UNPROCESSABLE_CONTENT, "answer_empty")
        if len(body.answer_text) > MAX_ANSWER_CHARS:
            raise _error(status.HTTP_422_UNPROCESSABLE_CONTENT, "answer_too_long")
        ideas = rubric_of(question)
        try:
            PracticeAttemptRepository(session, user.id).submit(
                attempt_id,
                now,
                hidden_ms=body.hidden_ms,
                reference_seconds=reference_time(session, question, len(ideas or [])),
                answer_text=body.answer_text,
                dont_remember=body.dont_remember,
            )
        except AttemptNotDraftError:
            session.rollback()  # another request submitted it first: grade that one
    session.commit()  # the answer and its timing are kept, whatever grading does next
    return _graded(session, user.id, attempt_id, ai, limiter, now)


@router.post("/attempts/{attempt_id}/regrade")
def regrade_attempt(
    attempt_id: uuid.UUID,
    user: VerifiedUser,
    session: DbSession,
    ai: Ai,
    limiter: Limiter,
    now: Now,
) -> PracticeView:
    """ "Chấm lại": grade a submitted answer that has no grade yet; a graded one is returned as it
    is, never paid for (or scheduled) twice."""
    _owned(session, user.id, attempt_id)
    return _graded(session, user.id, attempt_id, ai, limiter, now)


@router.post("/grades/{grade_id}/override")
def override(
    grade_id: uuid.UUID, body: PracticeOverrideIn, user: VerifiedUser, session: DbSession
) -> PracticeView:
    """ "Chấm sai": append a user grade; the practice schedule is rebuilt from `practice_log`."""
    try:
        grade = override_practice_grade(session, user.id, grade_id, body.verdict)
    except GradeNotFoundError as error:
        raise _error(status.HTTP_404_NOT_FOUND, "grade_not_found") from error
    except GradeNotCurrentError as error:
        raise _error(status.HTTP_409_CONFLICT, "grade_not_current") from error
    except GradeBusyError as error:
        raise _error(status.HTTP_409_CONFLICT, "grading_in_progress") from error
    attempt, question = _owned(session, user.id, grade.attempt_id)
    return _view(session, user.id, attempt, question, PracticeOutcome("graded", grade))


@router.post("/questions/{question_id}/worthless", status_code=status.HTTP_204_NO_CONTENT)
def worthless(question_id: uuid.UUID, user: VerifiedUser, session: DbSession, now: Now) -> Response:
    """ "Câu này vô giá trị": never asked again and its schedule stops; its log stays."""
    questions = QuestionRepository(session, user.id)
    question = questions.get(question_id)
    if question is None or SubjectRepository(session, user.id).get(question.subject_id) is None:
        raise _error(status.HTTP_404_NOT_FOUND, "question_not_found")
    questions.retire(question_id)
    remove(session, user.id, question_id, now)  # False for a question never attempted
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _may_call(limiter: Limiter, user_id: uuid.UUID) -> bool:
    try:
        limiter.enforce(GRADINGS_PER_USER, str(user_id))
    except (RateLimitedError, RateLimiterUnavailableError):
        return False
    return True


def _graded(
    session: DbSession,
    user_id: uuid.UUID,
    attempt_id: uuid.UUID,
    ai: Ai,
    limiter: Limiter,
    now: dt.datetime,
) -> PracticeView:
    try:
        outcome = grade_practice_attempt(
            session, user_id, attempt_id, ai, may_call_ai=lambda: _may_call(limiter, user_id)
        )
    except AttemptNotFoundError as error:
        raise _error(status.HTTP_404_NOT_FOUND, "attempt_not_found") from error
    except AttemptNotDraftError as error:
        raise _error(status.HTTP_409_CONFLICT, "attempt_not_submitted") from error
    GradeJobRepository(session, user_id).settle_practice(
        attempt_id, outcome.grading, outcome.failure, now
    )
    attempt, question = _owned(session, user_id, attempt_id)
    return _view(session, user_id, attempt, question, outcome)
