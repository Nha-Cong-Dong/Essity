"""Question bank import (T8.1b, US-14): POST /v1/subjects/{id}/question-banks/{document_id}/import.

The document is one the learner uploaded with the role `question_bank` and that ai-service has
read (`indexed`). Importing is allowed any time and as often as wanted: a question already stored
is skipped by its content hash (AC8). One call to ai-service splits the bank, suggests types and
links sections (batched, never one call per question); the model writes none of the questions or
answers. A quota or model stop stores nothing (AC9) and says so with a neutral line; the learner
imports again later, and what was stored never doubles.
"""

import json
import logging
import uuid
from typing import Annotated, Any, Literal, cast

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select

from core_api.api.attempts import GRADINGS_PER_USER, Limiter
from core_api.api.deps import Storage, VerifiedUser, verified_user
from core_api.api.ping import get_ai_client
from core_api.clients.ai_client import AiServiceClient, NotGraded
from core_api.clients.storage import StorageUnavailableError
from core_api.db.models import DocSection, Document, QuestionType
from core_api.db.session import DbSession
from core_api.domain.question_bank import MSG_FAILED, MSG_NOTHING, MSG_PENDING_AI
from core_api.domain.readiness import Ready, Waiting, display_line
from core_api.handlers.question_bank_parsed import store_parsed
from core_api.repositories.document import DocumentRepository
from core_api.repositories.question_list import QuestionListRepository
from core_api.repositories.subject import SubjectRepository
from core_api.security.rate_limit import RateLimitedError, RateLimiterUnavailableError

router = APIRouter(prefix="/v1", dependencies=[Depends(verified_user)])

_log = logging.getLogger(__name__)

Ai = Annotated[AiServiceClient, Depends(get_ai_client)]

# ai-service takes at most this much text and this many pages and sections (T8.1b).
MAX_PAGES_FILE_BYTES = 6 * 1024 * 1024
MAX_PAGES = 400
MAX_SECTIONS = 500
MAX_EXISTING_TYPES = 100


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


def _pages(storage: Storage, document: Document) -> list[dict[str, Any]]:
    """The page text ai-service wrote when it indexed the file. Raises 409 when there is none,
    413 when the bank is longer than one request can carry."""
    if document.page_text_key is None:
        raise _error(status.HTTP_409_CONFLICT, "document_not_ready")
    try:
        raw = storage.read_start(document.page_text_key, MAX_PAGES_FILE_BYTES + 1)
    except StorageUnavailableError as error:
        raise _error(status.HTTP_503_SERVICE_UNAVAILABLE, "storage_unavailable") from error
    if len(raw) > MAX_PAGES_FILE_BYTES:
        raise _error(413, "bank_too_large")
    try:
        data = json.loads(raw)
    except ValueError as error:
        raise _error(status.HTTP_409_CONFLICT, "document_not_ready") from error
    items: object = cast("dict[str, Any]", data).get("pages") if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise _error(status.HTTP_409_CONFLICT, "document_not_ready")
    pages: list[dict[str, Any]] = []
    for item in cast("list[Any]", items):
        entry = cast("dict[str, Any]", item) if isinstance(item, dict) else {}
        text = entry.get("text")
        pages.append(
            {
                "text": text[:200_000] if isinstance(text, str) else "",
                "needs_vision": entry.get("needs_vision") is True,
            }
        )
    if len(pages) > MAX_PAGES:
        raise _error(413, "bank_too_large")
    return pages


def _sections(session: DbSession, user_id: uuid.UUID, subject_id: uuid.UUID) -> list[DocSection]:
    """Leaf sections of the subject's textbook that count (not excluded), in outline order. A
    subject with no outline gives none: every question is then "chưa gắn mục" (AC5)."""
    parents = select(DocSection.parent_id).where(
        DocSection.user_id == user_id, DocSection.parent_id.is_not(None)
    )
    return list(
        session.scalars(
            select(DocSection)
            .join(Document, Document.id == DocSection.document_id)
            .where(
                DocSection.user_id == user_id,
                DocSection.subject_id == subject_id,
                Document.role == "textbook",
                DocSection.excluded.is_(False),
                DocSection.id.not_in(parents),
            )
            .order_by(DocSection.document_id, DocSection.ord, DocSection.id)
            .limit(MAX_SECTIONS)
        )
    )


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
    pages = _pages(storage, document)
    if not _may_call(limiter, user.id):
        return ImportOut(
            status="pending_ai", message=MSG_PENDING_AI, added=0, duplicates=0, unmapped=0
        )
    sections = _sections(session, user.id, subject_id)
    names = list(
        session.scalars(
            select(QuestionType.name)
            .where(QuestionType.user_id == user.id, QuestionType.subject_id == subject_id)
            .order_by(QuestionType.created_at)
            .limit(MAX_EXISTING_TYPES)
        )
    )
    reply = ai.parse_question_bank(
        {
            "user_id": str(user.id),
            "subject_id": str(subject_id),
            "pages": pages,
            "existing_types": names,
            "sections": [{"id": str(s.id), "title": s.title[:300]} for s in sections],
        }
    )
    if isinstance(reply, NotGraded):
        if reply.failure == "invalid":
            return ImportOut(status="failed", message=MSG_FAILED, added=0, duplicates=0, unmapped=0)
        return ImportOut(
            status="pending_ai", message=MSG_PENDING_AI, added=0, duplicates=0, unmapped=0
        )
    if reply.status == "pending_ai":
        return ImportOut(
            status="pending_ai", message=MSG_PENDING_AI, added=0, duplicates=0, unmapped=0
        )
    if not reply.questions:
        return ImportOut(status="empty", message=MSG_NOTHING, added=0, duplicates=0, unmapped=0)
    stored = store_parsed(session, user.id, document, reply, {s.id for s in sections})
    return ImportOut(
        status=reply.status,
        message=None,
        added=stored.added,
        duplicates=stored.duplicates,
        unmapped=stored.unmapped,
    )


class WaitingSectionOut(BaseModel):
    id: uuid.UUID
    number: str  # outline number, "3.4"
    title: str


class QuestionOut(BaseModel):
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
    questions: list[QuestionOut]


@router.get("/subjects/{subject_id}/questions")
def list_questions(
    subject_id: uuid.UUID, user: VerifiedUser, session: DbSession
) -> QuestionListOut:
    """The subject's bank questions with readiness (T8.2, US-14 AC3-AC6)."""
    if SubjectRepository(session, user.id).get(subject_id) is None:
        raise _error(status.HTTP_404_NOT_FOUND, "subject_not_found")
    listed = QuestionListRepository(session, user.id).list(subject_id)
    out: list[QuestionOut] = []
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
            QuestionOut(
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
