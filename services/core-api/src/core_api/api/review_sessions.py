"""The review session API, before grading (T2.9, US-04, US-08; plan
`t2.8-t2.9-t2.14-today-session.md`). A session's questions are fixed when it starts (plan C1);
one session is open per learning day (plan C4). Submitting stores the answer; grading it is
T2.13, so a submitted answer is "pending" here."""

import uuid
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict

from core_api.api.deps import Now, VerifiedUser, verified_user
from core_api.api.text import AnswerText
from core_api.db.models import Attempt
from core_api.db.session import DbSession
from core_api.domain.learning_day import learning_day
from core_api.domain.today import compose_today
from core_api.repositories.question import QuestionNotFoundError
from core_api.repositories.review import (
    AttemptNotDraftError,
    AttemptNotFoundError,
    AttemptRepository,
    ReviewSessionEndedError,
    ReviewSessionItemRepository,
    ReviewSessionNotFoundError,
    ReviewSessionRepository,
    SessionStep,
    session_counts,
)
from core_api.repositories.subject import SubjectNotFoundError, SubjectRepository
from core_api.repositories.today import TodayRepository

router = APIRouter(prefix="/v1", dependencies=[Depends(verified_user)])


class StartIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    subject_id: uuid.UUID | None = None


class SessionOut(BaseModel):
    id: uuid.UUID
    answered: int
    total: int


class SubjectRef(BaseModel):
    id: uuid.UUID
    name: str


class QuestionOut(BaseModel):
    id: uuid.UUID
    prompt: str
    subject: SubjectRef


class AttemptOut(BaseModel):
    id: uuid.UUID
    status: str
    answer_text: str
    dont_remember: bool


class CurrentOut(BaseModel):
    done: Literal[False] = False
    position: int
    total: int
    question: QuestionOut
    attempt: AttemptOut | None


class DoneOut(BaseModel):
    done: Literal[True] = True


class AnswerIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    answer_text: AnswerText
    dont_remember: bool


class SubmittedOut(BaseModel):
    status: Literal["submitted"] = "submitted"
    grading: Literal["pending"] = "pending"


class StoppedOut(BaseModel):
    answered: int
    total: int


def _error(code: int, detail: str) -> HTTPException:
    return HTTPException(status_code=code, detail=detail)


def _attempt_out(attempt: Attempt) -> AttemptOut:
    return AttemptOut(
        id=attempt.id,
        status=attempt.status,
        answer_text=attempt.answer_text,
        dont_remember=attempt.dont_remember,
    )


def _finished(session_id: uuid.UUID, user_id: uuid.UUID, session: DbSession) -> bool:
    answered, total = session_counts(
        ReviewSessionItemRepository(session, user_id).progress(session_id)
    )
    return answered == total


@router.post("/review-sessions", status_code=status.HTTP_201_CREATED)
def start_session(
    body: StartIn, user: VerifiedUser, session: DbSession, now: Now, response: Response
) -> SessionOut:
    tz = ZoneInfo(user.timezone)
    day = learning_day(now, tz, user.day_start_hour)
    sessions = ReviewSessionRepository(session, user.id)
    items = ReviewSessionItemRepository(session, user.id)
    found = sessions.open_on(day)
    if found is not None and _finished(found.id, user.id, session):
        # Every question answered, but "stop" never came (the tab closed): close it as completed,
        # so it does not hold today's one open slot (review #21).
        held = sessions.hold_for_update(found.id)
        if held is not None and held.ended_at is None and _finished(found.id, user.id, session):
            sessions.end(found.id, now, reason="completed")
        found = None
    if found is None:
        listed = SubjectRepository(session, user.id).list_with_exams()
        exams = {subject.id: exam.exam_date for subject, exam, _ in listed}
        if body.subject_id is not None and body.subject_id not in exams:
            raise _error(status.HTTP_404_NOT_FOUND, "subject_not_found")
        reads = TodayRepository(session, user.id)
        units = [u for u in reads.scheduled_units() if body.subject_id in (None, u.subject_id)]
        fresh = [q for q in reads.new_questions() if body.subject_id in (None, q.subject_id)]
        plan = compose_today(
            units, fresh, exams, now=now, tz=tz, day_start_hour=user.day_start_hour
        )
        if not plan.items:
            raise _error(status.HTTP_409_CONFLICT, "nothing_to_review")
        found, made = sessions.open_for_day(day, now)
        if made:
            items.add_all(found.id, [item.question_id for item in plan.items])
    else:
        response.status_code = status.HTTP_200_OK
    answered, total = session_counts(items.progress(found.id))
    return SessionOut(id=found.id, answered=answered, total=total)


def _open_steps(
    session_id: uuid.UUID, user_id: uuid.UUID, session: DbSession
) -> tuple[bool, list[SessionStep]]:
    """(ended, steps) of a session of this user; 404 when it is not theirs."""
    found = ReviewSessionRepository(session, user_id).get(session_id)
    if found is None:
        raise _error(status.HTTP_404_NOT_FOUND, "session_not_found")
    steps = ReviewSessionItemRepository(session, user_id).progress(session_id)
    return found.ended_at is not None, steps


def _current(steps: list[SessionStep]) -> SessionStep | None:
    return next((s for s in steps if s.askable and not s.answered), None)


@router.get("/review-sessions/{session_id}/current")
def current_question(
    session_id: uuid.UUID, user: VerifiedUser, session: DbSession
) -> CurrentOut | DoneOut:
    ended, steps = _open_steps(session_id, user.id, session)
    step = _current(steps)
    if ended or step is None:
        return DoneOut()
    answered, total = session_counts(steps)
    return CurrentOut(
        position=answered + 1,
        total=total,
        question=QuestionOut(
            id=step.question.id,
            prompt=step.question.prompt,
            subject=SubjectRef(id=step.subject.id, name=step.subject.name),
        ),
        attempt=_attempt_out(step.attempt) if step.attempt is not None else None,
    )


@router.post("/review-sessions/{session_id}/attempts", status_code=status.HTTP_201_CREATED)
def open_current_attempt(
    session_id: uuid.UUID, user: VerifiedUser, session: DbSession, response: Response
) -> AttemptOut:
    """The draft of the current question, made on first call. The server picks the question:
    a client cannot open an attempt on a question outside the session."""
    ended, steps = _open_steps(session_id, user.id, session)
    if ended:
        raise _error(status.HTTP_409_CONFLICT, "session_ended")
    step = _current(steps)
    if step is None:
        raise _error(status.HTTP_409_CONFLICT, "session_done")
    if step.attempt is not None:
        response.status_code = status.HTTP_200_OK
        return _attempt_out(step.attempt)
    try:
        attempt = AttemptRepository(session, user.id).create_draft(session_id, step.question.id)
    except ReviewSessionEndedError as error:
        raise _error(status.HTTP_409_CONFLICT, "session_ended") from error
    except (SubjectNotFoundError, QuestionNotFoundError) as error:
        raise _error(status.HTTP_404_NOT_FOUND, "subject_deleted") from error
    except ReviewSessionNotFoundError as error:
        raise _error(status.HTTP_404_NOT_FOUND, "session_not_found") from error
    return _attempt_out(attempt)


@router.put("/attempts/{attempt_id}/draft", status_code=status.HTTP_204_NO_CONTENT)
def save_draft(
    attempt_id: uuid.UUID, body: AnswerIn, user: VerifiedUser, session: DbSession
) -> None:
    try:
        AttemptRepository(session, user.id).save_draft(
            attempt_id, answer_text=body.answer_text, dont_remember=body.dont_remember
        )
    except AttemptNotFoundError as error:
        raise _error(status.HTTP_404_NOT_FOUND, "attempt_not_found") from error
    except ReviewSessionEndedError as error:
        raise _error(status.HTTP_409_CONFLICT, "session_ended") from error
    except AttemptNotDraftError as error:
        raise _error(status.HTTP_409_CONFLICT, "attempt_submitted") from error


@router.post("/attempts/{attempt_id}/submit")
def submit_attempt(
    attempt_id: uuid.UUID, body: AnswerIn, user: VerifiedUser, session: DbSession, now: Now
) -> SubmittedOut:
    """Save the last text and submit, in one write: nothing typed after the last draft save is
    lost. Submitting again returns the first submission, even once the session has ended."""
    attempts = AttemptRepository(session, user.id)
    found = attempts.get(attempt_id)
    if found is None:
        raise _error(status.HTTP_404_NOT_FOUND, "attempt_not_found")
    if found.status == "submitted":
        return SubmittedOut()
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
        return SubmittedOut()  # another request submitted it first
    return SubmittedOut()


@router.post("/review-sessions/{session_id}/stop")
def stop_session(
    session_id: uuid.UUID, user: VerifiedUser, session: DbSession, now: Now
) -> StoppedOut:
    """Close the session: "completed" when every question it can still ask is answered, else
    "user_stopped". The session is locked first, so a submit in flight is counted (plan D14).
    Stopping again changes nothing and answers the same."""
    sessions = ReviewSessionRepository(session, user.id)
    held = sessions.hold_for_update(session_id)
    if held is None:
        raise _error(status.HTTP_404_NOT_FOUND, "session_not_found")
    answered, total = session_counts(
        ReviewSessionItemRepository(session, user.id).progress(session_id)
    )
    if held.ended_at is None:
        sessions.end(session_id, now, reason="completed" if answered == total else "user_stopped")
    return StoppedOut(answered=answered, total=total)
