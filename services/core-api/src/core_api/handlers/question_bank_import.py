"""One question bank import, whoever starts it (T8.1b, T8.1c, US-14 AC8, AC9).

The route (`api.question_banks`) and the queued job (`jobs.question_bank_import`) both call
`run_import`: read the page text, ask ai-service once (batched, never one call per question),
store what came back. A quota or model stop stores nothing (AC9), so the import is queued and
runs again by itself when a turn is back (`enqueue_import`); what was stored never doubles (AC8).
Nothing here logs a question, answer or title (ADR-0013).
"""

import json
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal, Protocol, cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from core_api.clients.ai_client import NotGraded
from core_api.clients.bank_contract import BankReply
from core_api.clients.storage import ObjectStorage, StorageUnavailableError
from core_api.db.models import DocSection, Document, QuestionType
from core_api.domain.question_bank import MSG_FAILED, MSG_NOTHING, MSG_PENDING_AI
from core_api.handlers.question_bank_parsed import known_payload, store_parsed
from core_api.jobs.queue import enqueue_job
from core_api.repositories.doc_section import excluded_effective_ids

QUESTION_BANK_IMPORT = "question_bank_import"
# The import waits this long before it tries again when there is still no turn.
RETRY_DELAY = {"minutes": 10}

# ai-service takes at most this much text and this many pages and sections (T8.1b).
MAX_PAGES_FILE_BYTES = 6 * 1024 * 1024
MAX_PAGES = 400
MAX_SECTIONS = 500
MAX_EXISTING_TYPES = 100

_log = logging.getLogger("core_api.handlers")

Status = Literal["ok", "partial", "pending_ai", "failed", "empty"]


class BankPagesError(Exception):
    """The page text cannot be used. `code` is the API's error detail, `http` its status."""

    def __init__(self, http: int, code: str) -> None:
        super().__init__(code)
        self.http, self.code = http, code


class BankAi(Protocol):
    def parse_question_bank(self, payload: dict[str, Any]) -> BankReply | NotGraded: ...


@dataclass(frozen=True)
class ImportResult:
    status: Status
    message: str | None
    added: int = 0
    duplicates: int = 0
    unmapped: int = 0


def _pending() -> ImportResult:
    return ImportResult("pending_ai", MSG_PENDING_AI)


def read_pages(storage: ObjectStorage, document: Document) -> list[dict[str, Any]]:
    """The page text ai-service wrote when it indexed the file. Raises `BankPagesError`: 409 when
    there is none, 413 when the bank is longer than one request can carry, 503 for storage."""
    if document.page_text_key is None:
        raise BankPagesError(409, "document_not_ready")
    try:
        raw = storage.read_start(document.page_text_key, MAX_PAGES_FILE_BYTES + 1)
    except StorageUnavailableError as error:
        raise BankPagesError(503, "storage_unavailable") from error
    if len(raw) > MAX_PAGES_FILE_BYTES:
        raise BankPagesError(413, "bank_too_large")
    try:
        data = json.loads(raw)
    except ValueError as error:
        raise BankPagesError(409, "document_not_ready") from error
    items: object = cast("dict[str, Any]", data).get("pages") if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise BankPagesError(409, "document_not_ready")
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
        raise BankPagesError(413, "bank_too_large")
    return pages


def leaf_sections(session: Session, user_id: uuid.UUID, subject_id: uuid.UUID) -> list[DocSection]:
    """Leaf sections of the subject's textbook that count (not excluded), in outline order. A
    subject with no outline gives none: every question is then "chưa gắn mục" (AC5)."""
    parents = select(DocSection.parent_id).where(
        DocSection.user_id == user_id, DocSection.parent_id.is_not(None)
    )
    gone = excluded_effective_ids(session, user_id, subject_id)
    return list(
        session.scalars(
            select(DocSection)
            .join(Document, Document.id == DocSection.document_id)
            .where(
                DocSection.user_id == user_id,
                DocSection.subject_id == subject_id,
                Document.role == "textbook",
                DocSection.id.not_in(parents),
                DocSection.id.not_in(gone),
            )
            .order_by(DocSection.document_id, DocSection.ord, DocSection.id)
            .limit(MAX_SECTIONS)
        )
    )


def run_import(
    session: Session,
    user_id: uuid.UUID,
    document: Document,
    ai: BankAi,
    storage: ObjectStorage,
    may_call: Callable[[], bool],
) -> ImportResult:
    """Import the bank once. `pending_ai` means nothing was stored and the caller should queue
    the import; `failed` means the file can never be read (no queue)."""
    pages = read_pages(storage, document)
    if not may_call():
        return _pending()
    subject_id = document.subject_id
    sections = leaf_sections(session, user_id, subject_id)
    names = list(
        session.scalars(
            select(QuestionType.name)
            .where(QuestionType.user_id == user_id, QuestionType.subject_id == subject_id)
            .order_by(QuestionType.created_at)
            .limit(MAX_EXISTING_TYPES)
        )
    )
    reply = ai.parse_question_bank(
        {
            "user_id": str(user_id),
            "subject_id": str(subject_id),
            "pages": pages,
            "existing_types": names,
            "sections": [{"id": str(s.id), "title": s.title[:300]} for s in sections],
            "known": known_payload(session, user_id, subject_id, with_sections=bool(sections)),
        }
    )
    if isinstance(reply, NotGraded):
        return ImportResult("failed", MSG_FAILED) if reply.failure == "invalid" else _pending()
    if reply.status == "pending_ai":
        return _pending()
    if not reply.questions and reply.skipped == 0:
        return ImportResult("empty", MSG_NOTHING)
    stored = store_parsed(session, user_id, document, reply, {s.id for s in sections})
    return ImportResult(
        reply.status,
        None,
        added=stored.added,
        duplicates=stored.duplicates + reply.skipped,
        unmapped=stored.unmapped,
    )


def enqueue_import(
    session: Session,
    user_id: uuid.UUID,
    document: Document,
    *,
    queued_at: datetime | None = None,
    delayed: bool = False,
) -> bool:
    """Queue the import in the caller's transaction (AC9). One waiting job per bank: asking
    again while one waits adds none. `queued_at` is when the learner first asked; the job
    gives up a week later. Returns whether a job was added."""
    payload = {
        "user_id": str(user_id),
        "subject_id": str(document.subject_id),
        "document_id": str(document.id),
        "queued_at": (queued_at or datetime.now(UTC)).isoformat(),
    }
    added = enqueue_job(
        session,
        QUESTION_BANK_IMPORT,
        payload,
        queueing_lock=f"bank:{document.id}",
        schedule_in=RETRY_DELAY if delayed else None,
    )
    if added:
        _log.info("question bank import queued", extra={"outcome": "queued"})
    return added
