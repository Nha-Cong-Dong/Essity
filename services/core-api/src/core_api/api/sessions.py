"""Logging a study session (US-02, T4.12): the learner's sentence in, a card to confirm out.

`POST /v1/subjects/{id}/sessions` saves the sentence first (`description_raw`, layer 1: it stays
even if everything after fails), then asks ai-service to read it against the subject's indexed
documents. Whatever goes wrong (no answer, too slow, hard cap, an answer that does not fit the
documents) is a 201 with `card: "manual"`: the form the learner fills by hand (AC4), never a 5xx.

The whole call has a budget (`CREATE_BUDGET_SECONDS`) shared by reading the documents' files and
asking ai-service. Nothing of the sentence, the files or ai-service's answer is logged (ADR-0013).
"""

import datetime
import json
import uuid
from collections.abc import Callable
from datetime import timedelta
from time import monotonic
from typing import Annotated, Any, Literal, cast
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StrictStr

from core_api.api.deps import Now, Storage, VerifiedUser, verified_user
from core_api.api.ping import get_ai_client
from core_api.api.text import storable_text
from core_api.clients.ai_client import AiServiceClient, NotExtracted
from core_api.clients.extract_contract import Clarify, NoteOnly, Proposed
from core_api.clients.storage import ObjectStorage, StorageUnavailableError
from core_api.config import get_settings
from core_api.db.models import Document
from core_api.db.models.study_session import DESCRIPTION_MAX
from core_api.db.session import DbSession
from core_api.domain.learning_day import learning_day
from core_api.domain.study_session import (
    CREATE_BUDGET_SECONDS,
    ai_timeout,
    page_range_ok,
    studied_on_ok,
)
from core_api.repositories.document import DocumentRepository
from core_api.repositories.study_session import StudySessionRepository
from core_api.repositories.subject import SubjectNotFoundError
from core_api.security.rate_limit import RateLimit, RateLimiter, get_rate_limiter

router = APIRouter(prefix="/v1", dependencies=[Depends(verified_user)])

# ai-service takes at most 12 documents and 6000 toc entries in all (T4.10).
MAX_DOCUMENTS = 12
MAX_RANGES = 6
MAX_TOC_ENTRIES = 5000
MAX_TOC_TOTAL = 6000
# What a toc.json or page_labels.json may weigh for core to read it into a request.
FILE_MAX_BYTES = 1 << 20

ManualReason = Literal["failed", "disabled", "quota"]


def _not_blank(text: str) -> str:
    if not text.strip():
        raise ValueError("must not be blank")
    return text


Description = Annotated[
    StrictStr,
    Field(min_length=1, max_length=DESCRIPTION_MAX),
    AfterValidator(storable_text),
    AfterValidator(_not_blank),
]


class CreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: Description


class DocumentChoice(BaseModel):
    document_id: uuid.UUID
    short_name: str
    page_count: int


class CardRange(BaseModel):
    document_id: uuid.UUID
    short_name: str
    start_page: int
    end_page: int
    start_label: str | None
    end_label: str | None
    depth: Literal["deep", "skim", "unclear"]
    sections: list[str]
    basis_assumed_file: bool


class SessionCard(BaseModel):
    session_id: uuid.UUID
    status: Literal["draft"] = "draft"
    # proposed: ranges to confirm; note_only: nothing to read from a document (AC10); clarify:
    # one question back (AC5); manual: fill the form by hand (AC4).
    card: Literal["proposed", "note_only", "clarify", "manual"]
    studied_on: datetime.date | None = None
    ranges: list[CardRange] = []
    question: str | None = None
    reason: str | None = None
    candidate_document_ids: list[uuid.UUID] = []
    # Why the form is manual; null when there was nothing to ask (no indexed document yet).
    manual_reason: ManualReason | None = None
    # The subject's indexed documents, for the manual form's choices.
    documents: list[DocumentChoice]


def _error(code: int, detail: str) -> HTTPException:
    return HTTPException(status_code=code, detail=detail)


def _read_json(storage: ObjectStorage, key: str | None) -> object | None:
    """A derived file as JSON, or None when it is missing, too large or not JSON."""
    if key is None:
        return None
    try:
        raw = storage.read_start(key, FILE_MAX_BYTES + 1)
    except StorageUnavailableError:
        return None
    if len(raw) > FILE_MAX_BYTES:
        return None
    try:
        return json.loads(raw)
    except ValueError:
        return None


def _field(file: object, name: str) -> list[Any] | None:
    """`file[name]` when `file` is a JSON object and that is a list."""
    value = cast(dict[str, Any], file).get(name) if isinstance(file, dict) else None
    return cast(list[Any], value) if isinstance(value, list) else None


def _toc_entries(file: object, page_count: int) -> list[dict[str, Any]]:
    """`toc.json`'s entries made to fit ai-service's request: a real PDF is never refused."""
    out: list[dict[str, Any]] = []
    for item in (_field(file, "entries") or [])[:MAX_TOC_ENTRIES]:
        if not isinstance(item, dict):
            continue
        entry = cast(dict[str, Any], item)
        title, level, page = entry.get("title"), entry.get("level"), entry.get("page")
        if not isinstance(title, str) or not isinstance(level, int) or isinstance(level, bool):
            continue
        usable = isinstance(page, int) and not isinstance(page, bool) and 1 <= page <= page_count
        out.append(
            {
                "title": title[:500],
                "level": min(max(level, 0), 16),
                "page": page if usable else None,
            }
        )
    return out


def _labels(file: object, page_count: int) -> list[str] | None:
    labels = _field(file, "labels")
    if labels is None or len(labels) != page_count:
        return None
    if not all(isinstance(label, str) for label in labels):
        return None
    return [cast(str, label)[:128] for label in labels]


def _documents_payload(
    documents: list[Document],
    storage: ObjectStorage,
    last_end: dict[uuid.UUID, int],
    *,
    remaining: Callable[[], float],
) -> list[dict[str, Any]]:
    """The documents for ai-service, read one after another while budget is left. A document
    whose files cannot be read is left out: the learner can still pick it on the manual form."""
    out: list[dict[str, Any]] = []
    toc_total = 0
    # One read may take connect + read timeout; start none that could end past the budget.
    worst_read = 2 * get_settings().s3_timeout_seconds
    for document in documents:
        if remaining() < worst_read:
            break
        count = document.page_count
        toc = _read_json(storage, document.toc_key)
        if count is None or toc is None:
            continue
        entries = _toc_entries(toc, count)
        if toc_total + len(entries) > MAX_TOC_TOTAL:
            continue
        toc_total += len(entries)
        last = last_end.get(document.id)
        out.append(
            {
                "document_id": str(document.id),
                "short_name": document.short_name,
                "page_count": count,
                "page_labels": _labels(
                    _read_json(storage, document.page_labels_key)
                    if remaining() >= worst_read
                    else None,
                    count,
                ),
                "toc": entries,
                "last_end_page": last if last is not None and last <= count else None,
            }
        )
    return out


def _card(
    session_id: uuid.UUID,
    answer: Proposed | NoteOnly | Clarify,
    choices: list[DocumentChoice],
    today: datetime.date,
) -> tuple[str, SessionCard] | None:
    """The extraction to record and the card for ai-service's answer; None when the answer does
    not fit the subject's documents (another document, pages beyond the file): not shown."""
    known = {c.document_id: c for c in choices}
    if isinstance(answer, Clarify):
        return "clarify", SessionCard(
            session_id=session_id,
            card="clarify",
            question=answer.question,
            reason=answer.reason,
            candidate_document_ids=[i for i in answer.candidate_document_ids if i in known],
            documents=choices,
        )
    studied_on = answer.studied_on
    if studied_on is not None and not studied_on_ok(studied_on, today):
        studied_on = None
    if isinstance(answer, NoteOnly):
        return "note_only", SessionCard(
            session_id=session_id, card="note_only", studied_on=studied_on, documents=choices
        )
    if not answer.ranges or len(answer.ranges) > MAX_RANGES:
        return None
    ranges: list[CardRange] = []
    for r in answer.ranges:
        document = known.get(r.document_id)
        if document is None or not page_range_ok(r.start_page, r.end_page, document.page_count):
            return None
        ranges.append(
            CardRange(
                document_id=r.document_id,
                short_name=document.short_name,
                start_page=r.start_page,
                end_page=r.end_page,
                start_label=r.start_label,
                end_label=r.end_label,
                depth=r.depth,
                sections=r.sections,
                basis_assumed_file=r.basis_assumed_file,
            )
        )
    return "proposed", SessionCard(
        session_id=session_id,
        card="proposed",
        studied_on=studied_on,
        ranges=ranges,
        documents=choices,
    )


@router.post("/subjects/{subject_id}/sessions", response_model=SessionCard, status_code=201)
def create_session(
    subject_id: uuid.UUID,
    body: CreateRequest,
    user: VerifiedUser,
    session: DbSession,
    storage: Storage,
    ai_client: Annotated[AiServiceClient, Depends(get_ai_client)],
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
    now: Now,
    response: Response,
) -> SessionCard:
    """Save the sentence as a draft and return the card to confirm (US-02 AC3-AC5, AC11).

    Never a 5xx for the AI: no answer, over the budget, hard cap or an answer that does not fit
    the subject's documents all give `card: "manual"`. Errors: 404 `subject_not_found`; 429 with
    Retry-After (each call may cost AI money).
    """
    started = monotonic()

    def remaining() -> float:
        return CREATE_BUDGET_SECONDS - (monotonic() - started)

    response.headers["Cache-Control"] = "no-store"
    limiter.enforce(
        RateLimit("session_create", get_settings().session_creates_per_hour, timedelta(hours=1)),
        str(user.id),
    )
    drafts = StudySessionRepository(session, user.id)
    try:
        draft = drafts.create_draft(subject_id, body.description)
    except SubjectNotFoundError:
        raise _error(404, "subject_not_found") from None
    # The sentence is safe from here, whatever the AI does and however long it takes.
    session.commit()

    documents = DocumentRepository(session, user.id).indexed_of_subject(subject_id, MAX_DOCUMENTS)
    choices = [
        DocumentChoice(document_id=d.id, short_name=d.short_name, page_count=d.page_count)
        for d in documents
        if d.page_count is not None
    ]

    def manual(extraction: str, reason: ManualReason | None) -> SessionCard:
        draft.extraction = extraction
        return SessionCard(
            session_id=draft.id, card="manual", manual_reason=reason, documents=choices
        )

    if not choices:
        return manual("no_documents", None)
    sent = _documents_payload(
        documents, storage, drafts.last_end_pages(subject_id), remaining=remaining
    )
    timeout = ai_timeout(remaining())
    if not sent or timeout is None:
        return manual("failed", "failed")
    today = learning_day(now, ZoneInfo(user.timezone), user.day_start_hour)
    outcome = ai_client.extract_session(
        {
            "user_id": str(user.id),
            "subject_id": str(subject_id),
            "description": body.description,
            "today": today.isoformat(),
            "documents": sent,
        },
        timeout=timeout,
    )
    if isinstance(outcome, NotExtracted):
        if outcome.failure in ("disabled", "quota"):
            return manual(outcome.failure, outcome.failure)
        return manual("failed", "failed")
    built = _card(draft.id, outcome.response, choices, today)
    if built is None:
        return manual("failed", "failed")
    draft.extraction = built[0]
    return built[1]


class ProgressOut(BaseModel):
    session_id: uuid.UUID
    # waiting: confirmed, ai-service has not reported yet; processing; done; failed.
    state: Literal["waiting", "processing", "done", "failed"]
    step: Literal["reading_notes", "splitting_units", "anchoring", "writing_questions"] | None
    percent: int | None
    reason: Literal["unreadable", "llm_unavailable", "internal_error"] | None


_STATES = {"processing": "processing", "processed": "done", "failed": "failed"}


@router.get(
    "/sessions/{session_id}/progress",
    response_model=ProgressOut,
    responses={404: {"description": "session_not_found (another user's, or still a draft)"}},
)
def session_progress(
    session_id: uuid.UUID, user: VerifiedUser, session: DbSession, response: Response
) -> ProgressOut:
    """Where processing of a confirmed session stands, read from the server (T4.18, US-02 AC11).

    Errors: 403 for an unverified account; 404 `session_not_found` for another user's session and
    for a draft (nothing is processed before the confirm).
    """
    response.headers["Cache-Control"] = "no-store"
    study = StudySessionRepository(session, user.id).get(session_id)
    if study is None or study.status != "confirmed":
        raise _error(404, "session_not_found")
    return ProgressOut(
        session_id=study.id,
        state=_STATES.get(study.processing_state or "", "waiting"),  # type: ignore[arg-type]
        step=study.processing_step,  # type: ignore[arg-type]
        percent=study.processing_percent,
        reason=study.processing_reason,  # type: ignore[arg-type]
    )
