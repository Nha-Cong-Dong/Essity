"""Generated practice questions (T9.6b, US-17): press the button, see the candidates, keep or not.

- `POST /v1/subjects/{id}/generated-questions` on one question, one type or one studied outline
  leaf; 5 candidates per press, none stored unless they pass both filters; a second press while
  candidates wait (or while one runs) generates nothing.
- `GET` the candidates waiting for a choice.
- `POST /v1/generated-questions/{id}/keep` makes it a practice question ("Đưa vào luyện tập");
  `.../reject` ("Không giữ"): never suggested again. Removing a kept one is the existing
  `POST /v1/practice/questions/{id}/worthless`.
The reference answer and the rubric are not sent here: the learner sees them after answering.
The buttons are T8.7 (practice screen).
"""

import uuid
from typing import Annotated, Literal, Self

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, model_validator

from core_api.api.attempts import GRADINGS_PER_USER, Limiter
from core_api.api.deps import Now, VerifiedUser, verified_user
from core_api.api.ping import get_ai_client
from core_api.clients.ai_client import AiServiceClient
from core_api.db.models import Question
from core_api.db.session import DbSession
from core_api.repositories.generated_questions import GeneratedQuestionRepository
from core_api.repositories.subject import SubjectNotFoundError, SubjectRepository
from core_api.security.rate_limit import RateLimitedError, RateLimiterUnavailableError
from core_api.services.generated_questions import Kind, TargetNotFoundError, generate

router = APIRouter(prefix="/v1", dependencies=[Depends(verified_user)])

Ai = Annotated[AiServiceClient, Depends(get_ai_client)]


class GenerateIn(BaseModel):
    """Exactly one target."""

    model_config = ConfigDict(extra="forbid")

    question_id: uuid.UUID | None = None
    type_id: uuid.UUID | None = None
    section_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _one_target(self) -> Self:
        if sum(x is not None for x in (self.question_id, self.type_id, self.section_id)) != 1:
            raise ValueError("exactly one of question_id, type_id, section_id")
        return self


class CandidateOut(BaseModel):
    id: uuid.UUID
    prompt: str
    type_id: uuid.UUID | None
    label: Literal["Câu sinh thêm"] = "Câu sinh thêm"


class GeneratedSetOut(BaseModel):
    status: Literal["ok", "empty", "pending_ai", "failed", "running"]
    message: str | None  # the neutral line the screen shows, written by the backend
    candidates: list[CandidateOut]


def _out(question: Question) -> CandidateOut:
    return CandidateOut(id=question.id, prompt=question.prompt, type_id=question.type_id)


def _may_call(limiter: Limiter, user_id: uuid.UUID) -> bool:
    try:
        limiter.enforce(GRADINGS_PER_USER, str(user_id))
    except (RateLimitedError, RateLimiterUnavailableError):
        return False
    return True


def _not_found(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


@router.post("/subjects/{subject_id}/generated-questions")
def generate_questions(
    subject_id: uuid.UUID,
    body: GenerateIn,
    user: VerifiedUser,
    session: DbSession,
    now: Now,
    ai: Ai,
    limiter: Limiter,
) -> GeneratedSetOut:
    kind: Kind
    if body.question_id is not None:
        kind, target_id = "question", body.question_id
    elif body.type_id is not None:
        kind, target_id = "type", body.type_id
    else:
        assert body.section_id is not None
        kind, target_id = "section", body.section_id
    try:
        outcome = generate(
            session,
            user.id,
            subject_id,
            kind,
            target_id,
            ai,
            now,
            may_call=lambda: _may_call(limiter, user.id),
        )
    except SubjectNotFoundError as error:
        raise _not_found("subject_not_found") from error
    except TargetNotFoundError as error:
        raise _not_found("target_not_found") from error
    return GeneratedSetOut(
        status=outcome.status,
        message=outcome.message,
        candidates=[_out(q) for q in outcome.candidates],
    )


@router.get("/subjects/{subject_id}/generated-questions")
def waiting_candidates(
    subject_id: uuid.UUID, user: VerifiedUser, session: DbSession
) -> list[CandidateOut]:
    if SubjectRepository(session, user.id).get(subject_id) is None:
        raise _not_found("subject_not_found")
    repo = GeneratedQuestionRepository(session, user.id)
    return [_out(q) for q in repo.open_of_subject(subject_id)]


@router.post("/generated-questions/{question_id}/keep", status_code=status.HTTP_204_NO_CONTENT)
def keep(question_id: uuid.UUID, user: VerifiedUser, session: DbSession, now: Now) -> Response:
    """Đưa vào luyện tập: the question becomes a practice question (its schedule starts at the
    first attempt, T8.3). Keeping twice keeps the first time."""
    question = GeneratedQuestionRepository(session, user.id).candidate(question_id)
    if question is None:
        raise _not_found("question_not_found")
    if question.status != "active" or question.quality_status != "ok":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="question_retired")
    if question.kept_at is None:
        question.kept_at = now
        session.flush()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/generated-questions/{question_id}/reject", status_code=status.HTTP_204_NO_CONTENT)
def reject(question_id: uuid.UUID, user: VerifiedUser, session: DbSession) -> Response:
    """Không giữ: retired and marked rejected; its text stays in the duplicate checks, so it is
    never suggested again. A kept question is removed by `worthless`, not here."""
    question = GeneratedQuestionRepository(session, user.id).candidate(question_id)
    if question is None:
        raise _not_found("question_not_found")
    if question.kept_at is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="question_kept")
    question.status = "retired"
    question.quality_status = "rejected"
    session.flush()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
