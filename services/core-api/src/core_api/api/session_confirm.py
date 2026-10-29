"""Confirming a study session (US-02 AC7, T4.12): the draft becomes a session, in one transaction.

`POST /v1/sessions/{id}/confirm` takes the card as the learner left it (ranges, notes, study day)
and writes, together: the session's ranges, its note files, its dates, and the event
`session.confirmed.v1` in the outbox (with the subject's existing units). Any failure, the
enqueue included, rolls all of it back and the session stays a draft. The client sends no
object key: the server builds it from the file's SHA-256 (ADR-0012), and the file must already
be in the store with the declared size.

Nothing of the description or the notes is logged (ADR-0013).
"""

import datetime
import uuid
from datetime import timedelta
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StrictInt, StrictStr

from core_api.api.deps import Now, Storage, VerifiedUser, verified_user
from core_api.api.text import storable_text
from core_api.clients.storage import StorageUnavailableError
from core_api.config import get_settings
from core_api.db.models import Document, NoteFile, SessionRange, StudySession
from core_api.db.session import DbSession
from core_api.domain.learning_day import learning_day
from core_api.domain.study_session import (
    NOTE_MAGIC_MAX,
    cut_summary,
    ensure_ranges_ordered,
    looks_like_note,
    note_key,
    page_range_ok,
    studied_on_ok,
)
from core_api.messaging.envelope import ExistingUnit, SessionConfirmed
from core_api.messaging.envelope import NoteFile as EventNote
from core_api.messaging.envelope import SessionRange as EventRange
from core_api.messaging.outbox import enqueue_event
from core_api.repositories.document import DocumentRepository
from core_api.repositories.note_upload import NoteUploadRepository
from core_api.repositories.study_session import StudySessionRepository
from core_api.repositories.subject import SubjectNotFoundError, SubjectRepository
from core_api.repositories.unit import KnowledgeUnitRepository
from core_api.security.rate_limit import RateLimit, RateLimiter, get_rate_limiter

router = APIRouter(prefix="/v1", dependencies=[Depends(verified_user)])

MAX_RANGES = 6
MAX_NOTES = 20
MAX_PAGE = 5000
# session.confirmed.v1 carries at most this many units of the subject.
MAX_EXISTING_UNITS = 500

Depth = Literal["deep", "skim", "unclear"]
Mime = Literal["image/jpeg", "image/png", "application/pdf", "text/plain", "text/markdown"]
Label = Annotated[StrictStr, Field(min_length=1, max_length=40), AfterValidator(storable_text)]
Sha256 = Annotated[StrictStr, Field(pattern=r"^[0-9a-f]{64}$"), AfterValidator(storable_text)]


class RangeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: uuid.UUID
    start_page: StrictInt = Field(ge=1, le=MAX_PAGE)
    end_page: StrictInt = Field(ge=1, le=MAX_PAGE)
    depth: Depth
    start_label: Label | None = None
    end_label: Label | None = None


class NoteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sha256: Sha256
    mime: Mime
    size_bytes: StrictInt = Field(gt=0)


class ConfirmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # The day actually studied (Q14); empty means today.
    studied_on: datetime.date | None = None
    ranges: list[RangeIn] = Field(default=[], max_length=MAX_RANGES)
    notes: list[NoteIn] = Field(default=[], max_length=MAX_NOTES)


class RangeOut(BaseModel):
    document_id: uuid.UUID
    start_page: int
    end_page: int
    start_label: str | None
    end_label: str | None
    depth: Depth


class NoteOut(BaseModel):
    sha256: str
    mime: str
    size_bytes: int


class SessionOut(BaseModel):
    session_id: uuid.UUID
    subject_id: uuid.UUID
    status: Literal["confirmed"] = "confirmed"
    studied_on: datetime.date
    learning_day: datetime.date
    confirmed_at: datetime.datetime
    ranges: list[RangeOut]
    notes: list[NoteOut]


def _error(code: int, detail: str) -> HTTPException:
    return HTTPException(status_code=code, detail=detail)


def _out(drafts: StudySessionRepository, session: StudySession) -> SessionOut:
    assert session.studied_on and session.learning_day and session.confirmed_at
    return SessionOut(
        session_id=session.id,
        subject_id=session.subject_id,
        studied_on=session.studied_on,
        learning_day=session.learning_day,
        confirmed_at=session.confirmed_at,
        ranges=[
            RangeOut(
                document_id=r.document_id,
                start_page=r.start_page,
                end_page=r.end_page,
                start_label=r.start_label,
                end_label=r.end_label,
                depth=r.depth,  # pyright: ignore[reportArgumentType]
            )
            for r in drafts.ranges_of(session.id)
        ],
        notes=[
            NoteOut(sha256=n.sha256, mime=n.mime, size_bytes=n.size_bytes)
            for n in drafts.notes_of(session.id)
        ],
    )


def _documents_of_ranges(
    body: ConfirmRequest, documents: DocumentRepository, subject_id: uuid.UUID
) -> dict[uuid.UUID, Document]:
    """The documents the ranges name, each this user's, of this subject and indexed. 404
    `document_not_found` for any other (another user's included: nothing tells them apart)."""
    found: dict[uuid.UUID, Document] = {}
    for item in body.ranges:
        if item.document_id in found:
            continue
        document = documents.get(item.document_id)
        if document is None or document.subject_id != subject_id:
            raise _error(404, "document_not_found")
        if document.status != "indexed" or document.page_count is None:
            raise _error(409, "not_indexed")
        found[document.id] = document
    return found


def _check_ranges(body: ConfirmRequest, found: dict[uuid.UUID, Document]) -> None:
    seen: set[tuple[uuid.UUID, int, int]] = set()
    for item in body.ranges:
        count = found[item.document_id].page_count or 0
        key = (item.document_id, item.start_page, item.end_page)
        if not page_range_ok(item.start_page, item.end_page, count) or key in seen:
            raise _error(422, "bad_range")
        seen.add(key)


def _distinct_notes(body: ConfirmRequest) -> list[NoteIn]:
    """The same file twice is one note (AC13); the same hash with another type or size is a
    mistake, not a second file."""
    by_sha: dict[str, NoteIn] = {}
    for note in body.notes:
        first = by_sha.setdefault(note.sha256, note)
        if (first.mime, first.size_bytes) != (note.mime, note.size_bytes):
            raise _error(422, "bad_note")
    return list(by_sha.values())


@router.post(
    "/sessions/{session_id}/confirm",
    response_model=SessionOut,
    responses={
        404: {"description": "session_not_found, subject_not_found or document_not_found"},
        409: {"description": "upload_incomplete (a note not stored yet) or not_indexed"},
        422: {"description": "bad_range, bad_date, bad_note, size_mismatch or content_mismatch"},
    },
)
def confirm_session(
    session_id: uuid.UUID,
    body: ConfirmRequest,
    user: VerifiedUser,
    session: DbSession,
    storage: Storage,
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
    now: Now,
    response: Response,
) -> SessionOut:
    """Confirm the card: write the session's ranges, notes and dates and announce it to
    ai-service (`session.confirmed.v1`), all in one transaction. Confirming again returns the
    session as it was saved and announces nothing more.

    Errors: 404 `session_not_found` (another user's too), `subject_not_found` (deleted since),
    `document_not_found` (another subject's or user's too); 409 `not_indexed`, `upload_incomplete`;
    422 `bad_range`, `bad_date`, `bad_note`, `size_mismatch`, `content_mismatch`; 429 with
    Retry-After (each confirm calls the store once per note, R60a); 503 `storage_unavailable`.

    Locks the subject FOR SHARE, then the session FOR UPDATE (the order `create_draft` and a
    subject's delete agree on).
    """
    response.headers["Cache-Control"] = "no-store"
    limiter.enforce(
        RateLimit("session_confirm", get_settings().session_confirms_per_hour, timedelta(hours=1)),
        str(user.id),
    )
    drafts = StudySessionRepository(session, user.id)
    found = drafts.get(session_id)
    if found is None:
        raise _error(404, "session_not_found")
    try:
        SubjectRepository(session, user.id).hold_for_share(found.subject_id)
    except SubjectNotFoundError:
        raise _error(404, "subject_not_found") from None
    draft = drafts.lock(session_id)
    if draft is None:
        raise _error(404, "session_not_found")
    if draft.status == "confirmed":
        return _out(drafts, draft)

    # Everything that can refuse comes before the first write.
    today = learning_day(now, ZoneInfo(user.timezone), user.day_start_hour)
    studied_on = body.studied_on or today
    if not studied_on_ok(studied_on, today):
        raise _error(422, "bad_date")
    documents = _documents_of_ranges(body, DocumentRepository(session, user.id), draft.subject_id)
    _check_ranges(body, documents)
    notes = _distinct_notes(body)
    keys = {n.sha256: note_key(user.id, draft.id, n.sha256, n.mime) for n in notes}
    # Held until commit: cleanup skips these rows while this confirm decides about their files.
    pending = NoteUploadRepository(session, user.id)
    held = pending.lock_of_session(draft.id, [n.sha256 for n in notes])
    try:
        for note in notes:
            stored = storage.head(keys[note.sha256])
            if stored is None:
                raise _error(409, "upload_incomplete")
            if stored.size != note.size_bytes:
                raise _error(422, "size_mismatch")
            if stored.sha256 is not None and stored.sha256 != note.sha256:
                raise _error(422, "content_mismatch")
            start = storage.read_start(keys[note.sha256], NOTE_MAGIC_MAX)
            if not looks_like_note(note.mime, start):
                raise _error(422, "content_mismatch")
    except StorageUnavailableError:
        raise _error(503, "storage_unavailable") from None

    for position, item in enumerate(body.ranges):
        session.add(
            SessionRange(
                user_id=user.id,
                session_id=draft.id,
                document_id=item.document_id,
                start_page=item.start_page,
                end_page=item.end_page,
                start_label=item.start_label,
                end_label=item.end_label,
                depth=item.depth,
                position=position,
            )
        )
    for note in notes:
        session.add(
            NoteFile(
                user_id=user.id,
                session_id=draft.id,
                object_key=keys[note.sha256],
                sha256=note.sha256,
                mime=note.mime,
                size_bytes=note.size_bytes,
            )
        )
    for row in held:  # accounted by their note_file from now on
        session.delete(row)
    draft.status = "confirmed"
    draft.studied_on = studied_on
    draft.learning_day = today
    draft.confirmed_at = now
    session.flush()

    units = KnowledgeUnitRepository(session, user.id).for_event(
        draft.subject_id, MAX_EXISTING_UNITS
    )
    ensure_ranges_ordered((r.start_page, r.end_page) for r in body.ranges)
    enqueue_event(
        session,
        SessionConfirmed(
            study_session_id=draft.id,
            subject_id=draft.subject_id,
            ranges=[
                EventRange(
                    document_id=r.document_id, first=r.start_page, last=r.end_page, depth=r.depth
                )
                for r in body.ranges
            ],
            notes=[EventNote(object_key=keys[n.sha256], mime=n.mime) for n in notes],
            existing_units=[
                ExistingUnit(unit_id=u.id, title=u.title, summary=cut_summary(u.summary))
                for u in units
            ],
        ),
        user_id=user.id,
        now=now,
    )
    return _out(drafts, draft)
