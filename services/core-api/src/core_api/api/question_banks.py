"""Question bank import (T8.1b, US-14): POST /v1/subjects/{id}/question-banks/{document_id}/import.

The document is one the learner uploaded with the role `question_bank` and that ai-service has
read (`indexed`). Importing is allowed any time and as often as wanted: a question already stored
is skipped by its content hash (AC8). One call to ai-service splits the bank, suggests types and
links sections (batched, never one call per question); the model writes none of the questions or
answers. A quota or model stop stores nothing (AC9) and says so with a neutral line; the learner
imports again later, and what was stored never doubles.
"""

import logging
import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from core_api.api.attempts import GRADINGS_PER_USER, Limiter
from core_api.api.deps import Storage, VerifiedUser, verified_user
from core_api.api.ping import get_ai_client
from core_api.clients.ai_client import AiServiceClient
from core_api.db.session import DbSession
from core_api.domain.readiness import Ready, Waiting, display_line
from core_api.handlers.question_bank_import import BankPagesError, enqueue_import, run_import
from core_api.repositories.document import DocumentRepository
from core_api.repositories.question_list import QuestionListRepository
from core_api.repositories.subject import SubjectRepository
from core_api.security.rate_limit import RateLimitedError, RateLimiterUnavailableError

router = APIRouter(prefix="/v1", dependencies=[Depends(verified_user)])

_log = logging.getLogger(__name__)

Ai = Annotated[AiServiceClient, Depends(get_ai_client)]


class ImportOut(BaseModel):
    status: Literal["ok", "partial", "pending_ai", "failed", "empty"]
    message: str | None  # the neutral line the screen shows, written by the backend
    added: int
    duplicates: int
    unmapped: int  # added questions left without a section: "chưa gắn mục"


def _error(code: int, detail: str) -> HTTPException:
    return HTTPException(status_code=code, detail=detail)


def _may_call(limiter: Limiter, user_id: uuid.UUID) -> bool:
    try:
        limiter.enforce(GRADINGS_PER_USER, str(user_id))
    except (RateLimitedError, RateLimiterUnavailableError):
        return False
    return True


@router.post("/subjects/{subject_id}/question-banks/{document_id}/import")
def import_bank(
    subject_id: uuid.UUID,
    document_id: uuid.UUID,
    user: VerifiedUser,
    session: DbSession,
    ai: Ai,
    storage: Storage,
    limiter: Limiter,
) -> ImportOut:
    if SubjectRepository(session, user.id).get(subject_id) is None:
        raise _error(status.HTTP_404_NOT_FOUND, "subject_not_found")
    document = DocumentRepository(session, user.id).get(document_id)
    if document is None or document.subject_id != subject_id:
        raise _error(status.HTTP_404_NOT_FOUND, "document_not_found")
    if document.role != "question_bank":
        raise _error(status.HTTP_409_CONFLICT, "not_a_question_bank")
    if document.status != "indexed":
        raise _error(status.HTTP_409_CONFLICT, "document_not_ready")

    def may_call() -> bool:
        return _may_call(limiter, user.id)

    try:
        result = run_import(session, user.id, document, ai, storage, may_call)
    except BankPagesError as error:
        raise _error(error.http, error.code) from error
    if result.status == "pending_ai":
        enqueue_import(session, user.id, document)  # AC9: runs by itself when a turn is back
    return ImportOut(
        status=result.status,
        message=result.message,
        added=result.added,
        duplicates=result.duplicates,
        unmapped=result.unmapped,
    )


class WaitingSectionOut(BaseModel):
    id: uuid.UUID
    number: str  # outline number, "3.4"
    title: str


class BankQuestionOut(BaseModel):
    id: uuid.UUID
    number: int | None  # place in the bank: "Câu 7"
    prompt: str
    type_name: str  # "" when the question has no type
    origin: Literal["bank", "generated"]
    answer_source: Literal["bank", "ai"]
    status: Literal["ready", "waiting", "unlinked"]
    line: str  # the one neutral line the list shows
    waiting_sections: list[WaitingSectionOut]


class TypeCountOut(BaseModel):
    name: str
    count: int


class QuestionListOut(BaseModel):
    total: int
    ready: int
    types: list[TypeCountOut]
    questions: list[BankQuestionOut]


@router.get("/subjects/{subject_id}/questions")
def list_questions(
    subject_id: uuid.UUID, user: VerifiedUser, session: DbSession
) -> QuestionListOut:
    """The subject's bank questions with readiness (T8.2, US-14 AC3-AC6)."""
    if SubjectRepository(session, user.id).get(subject_id) is None:
        raise _error(status.HTTP_404_NOT_FOUND, "subject_not_found")
    listed = QuestionListRepository(session, user.id).list_for_subject(subject_id)
    out: list[BankQuestionOut] = []
    counts: dict[str, int] = {}
    for q in listed:
        counts[q.type_name] = counts.get(q.type_name, 0) + 1
        state = q.state
        waiting = (
            [
                WaitingSectionOut(id=s.id, number=s.label, title=q.waiting_titles[s.id])
                for s in state.sections
            ]
            if isinstance(state, Waiting)
            else []
        )
        out.append(
            BankQuestionOut(
                id=q.id,
                number=q.number,
                prompt=q.prompt,
                type_name=q.type_name,
                origin="generated" if q.origin == "generated" else "bank",
                answer_source="ai" if q.answer_source == "ai" else "bank",
                status="ready"
                if isinstance(state, Ready)
                else "waiting"
                if isinstance(state, Waiting)
                else "unlinked",
                line=display_line(state),
                waiting_sections=waiting,
            )
        )
    return QuestionListOut(
        total=len(out),
        ready=sum(1 for q in out if q.status == "ready"),
        types=[TypeCountOut(name=n, count=c) for n, c in counts.items()],
        questions=out,
    )
