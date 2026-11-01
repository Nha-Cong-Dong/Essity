"""Reviewing the draft cards of a study session (T7.8, US-02b AC6-AC9, AC14).

    GET    /v1/sessions/{id}/drafts          the drafts, with anchors and revisions (AC14)
    POST   /v1/sessions/{id}/drafts          add a card by hand
    POST   /v1/sessions/{id}/drafts/merge    merge drafts (deterministic, no LLM)
    POST   /v1/sessions/{id}/drafts/save     Save: the cards the screen shows, one transaction
    GET    /v1/drafts/{id}
    PATCH  /v1/drafts/{id}                   edit in place; `If-Match: <version>`
    DELETE /v1/drafts/{id}                   discard (retired, undo for 7 days)
    POST   /v1/drafts/{id}/undo
    POST   /v1/drafts/{id}/split             `If-Match: <version>`

An edit or split without `If-Match` is 428, a stale version is 409 `unit_changed_elsewhere`
("thẻ đã đổi ở nơi khác"). Another user's id is 404, like an unknown one. Everything is a thin
layer over `domain.unit_review.UnitReviewService`; the rules live there. Nothing the learner wrote
is logged (ADR-0013).
"""

import json
import logging
import re
import uuid
from typing import Annotated, Any, Literal, cast
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StrictInt, StrictStr

from core_api.api.deps import Now, Storage, VerifiedUser, verified_user
from core_api.api.text import DbText, storable_text
from core_api.clients.storage import StorageUnavailableError
from core_api.db.models import Anchor, KnowledgeUnit, UnitRevision
from core_api.db.session import DbSession
from core_api.domain import unit_review as review
from core_api.repositories.document import DocumentRepository
from core_api.repositories.study_session import StudySessionRepository
from core_api.repositories.submission import SubmissionRepository

router = APIRouter(prefix="/v1", dependencies=[Depends(verified_user)])
_log = logging.getLogger("core_api.api.drafts")

MAX_CONTEXT_BYTES = 1_000_000
Kind = Literal["concept", "mechanism", "comparison", "formula", "example"]
Title = Annotated[StrictStr, Field(min_length=1, max_length=200), AfterValidator(storable_text)]
Body = Annotated[StrictStr, Field(min_length=1, max_length=4000), AfterValidator(storable_text)]
_VERSION = re.compile(r'(?:W/)?"?(\d{1,9})"?')


class AnchorOut(BaseModel):
    id: uuid.UUID
    source: str
    document_id: uuid.UUID | None
    page_no: int | None
    start: int | None
    end: int | None
    quote_text: str


class RevisionOut(BaseModel):
    rev: int
    origin: str
    content: dict[str, str]


class DraftOut(BaseModel):
    id: uuid.UUID
    session_id: uuid.UUID | None
    title: str
    content: str
    kind: str
    status: str
    version: int
    section_ids: list[uuid.UUID]
    anchors: list[AnchorOut]
    revisions: list[RevisionOut]


class DraftsOut(BaseModel):
    drafts: list[DraftOut]
    # queued / processing / pending_ai / done / failed, or None before a submission. pending_ai
    # means "waiting for the AI": the screen says so neutrally and editing stays open.
    submission_status: str | None


class AddIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: Title
    content: Body
    kind: Kind
    section_id: uuid.UUID | None = None


class EditIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: Title | None = None
    content: Body | None = None
    kind: Kind | None = None


class MergeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    unit_ids: list[uuid.UUID] = Field(min_length=2, max_length=50)


class PartIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: Title
    content: Body
    anchor_ids: list[uuid.UUID] = Field(default=[], max_length=50)


class SplitIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    parts: list[PartIn] = Field(min_length=2, max_length=10)


class SaveItemIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    unit_id: uuid.UUID
    version: StrictInt = Field(ge=1)


class SaveIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    units: list[SaveItemIn] = Field(min_length=1, max_length=200)


class SaveOut(BaseModel):
    saved: list[uuid.UUID]


def _error(code: int, detail: str | dict[str, str]) -> HTTPException:
    return HTTPException(status_code=code, detail=detail)


def _changed() -> HTTPException:
    return _error(
        409, {"code": "unit_changed_elsewhere", "message": review.UnitChangedElsewhere.message}
    )


def _version(if_match: str | None) -> int:
    if if_match is None:
        raise _error(428, "if_match_required")
    found = _VERSION.fullmatch(if_match.strip())
    if found is None:
        raise _error(400, "bad_if_match")
    return int(found.group(1))


def _out(view: review.DraftView) -> DraftOut:
    unit: KnowledgeUnit = view.unit
    return DraftOut(
        id=unit.id,
        session_id=unit.session_id,
        title=unit.title,
        content=unit.summary,
        kind=unit.kind,
        status=unit.status,
        version=unit.version,
        section_ids=view.section_ids,
        anchors=[_anchor_out(a) for a in view.anchors],
        revisions=[_revision_out(r) for r in view.revisions],
    )


def _anchor_out(a: Anchor) -> AnchorOut:
    return AnchorOut(
        id=a.id,
        source=a.source,
        document_id=a.document_id,
        page_no=a.page_no,
        start=a.char_start,
        end=a.char_end,
        quote_text=a.quote_text,
    )


def _revision_out(r: UnitRevision) -> RevisionOut:
    return RevisionOut(rev=r.rev, origin=r.origin, content=r.content)


def _one(service: review.UnitReviewService, unit: KnowledgeUnit) -> DraftOut:
    return _out(service.get(unit.id))


@router.get("/sessions/{session_id}/drafts")
def list_drafts(session_id: uuid.UUID, user: VerifiedUser, session: DbSession) -> DraftsOut:
    service = review.UnitReviewService(session, user.id)
    try:
        views = service.drafts(session_id)
    except review.SessionNotFound:
        raise _error(404, "session_not_found") from None
    submission = SubmissionRepository(session, user.id).of_session(session_id)
    return DraftsOut(
        drafts=[_out(v) for v in views],
        submission_status=submission.status if submission is not None else None,
    )


@router.post("/sessions/{session_id}/drafts", status_code=201)
def add_draft(
    session_id: uuid.UUID, body: AddIn, user: VerifiedUser, session: DbSession
) -> DraftOut:
    service = review.UnitReviewService(session, user.id)
    try:
        unit = service.add(
            session_id,
            title=body.title,
            content=body.content,
            kind=body.kind,
            section_id=body.section_id,
        )
    except review.SessionNotFound:
        raise _error(404, "session_not_found") from None
    return _one(service, unit)


@router.post("/sessions/{session_id}/drafts/merge")
def merge_drafts(
    session_id: uuid.UUID, body: MergeIn, user: VerifiedUser, session: DbSession
) -> DraftOut:
    service = review.UnitReviewService(session, user.id)
    try:
        unit = service.merge(session_id, body.unit_ids)
    except (review.SessionNotFound, review.UnitNotFound):
        raise _error(404, "unit_not_found") from None
    except review.NotADraft:
        raise _error(409, "not_a_draft") from None
    except ValueError:
        raise _error(422, "merge_needs_two") from None
    return _one(service, unit)


@router.post("/sessions/{session_id}/drafts/save")
def save_drafts(
    session_id: uuid.UUID,
    body: SaveIn,
    user: VerifiedUser,
    session: DbSession,
    now: Now,
    storage: Storage,
) -> SaveOut:
    study = StudySessionRepository(session, user.id).get(session_id)
    if study is None:
        raise _error(404, "session_not_found")
    ranges = _context_ranges(session, user.id, study.id, study.subject_id, storage)
    service = review.UnitReviewService(session, user.id)
    try:
        result = service.save(
            session_id,
            [review.SaveItem(i.unit_id, i.version) for i in body.units],
            now=now,
            tz=ZoneInfo(user.timezone),
            day_start_hour=user.day_start_hour,
            ranges=ranges,
        )
    except (review.SessionNotFound, review.UnitNotFound):
        raise _error(404, "unit_not_found") from None
    except review.UnitChangedElsewhere:
        raise _changed() from None
    except review.NotADraft:
        raise _error(409, "not_a_draft") from None
    return SaveOut(saved=result.saved)


def _context_ranges(
    session: DbSession,
    user_id: uuid.UUID,
    study_session_id: uuid.UUID,
    subject_id: uuid.UUID,
    storage: Storage,
) -> list[review.NewRange]:
    """The page ranges the learner mentioned, from the submission's context file. Read before any
    lock or write; the file is only a hint, so anything odd in it is skipped."""
    submission = SubmissionRepository(session, user_id).of_session(study_session_id)
    if submission is None:
        return []
    key = f"users/{user_id}/sessions/{study_session_id}/context/{submission.id}.json"
    try:
        raw = storage.read(key, max_bytes=MAX_CONTEXT_BYTES)
    except StorageUnavailableError:
        raise _error(503, "storage_unavailable") from None
    if raw is None:
        return []
    try:
        mentions: Any = json.loads(raw).get("mentions", [])
    except (ValueError, AttributeError):
        _log.warning("context unreadable", extra={"study_session_id": str(study_session_id)})
        return []
    documents = {d.id for d in DocumentRepository(session, user_id).of_subject(subject_id)}
    found: list[review.NewRange] = []
    items: list[Any] = cast(list[Any], mentions) if isinstance(mentions, list) else []
    for item in items:
        try:
            document_id = uuid.UUID(str(item["document_id"]))
            first: Any = item["first_page"]
            last: Any = item["last_page"]
        except (KeyError, TypeError, ValueError):
            continue
        if (
            document_id in documents
            and type(first) is int
            and type(last) is int
            and 1 <= first <= last
        ):
            found.append(review.NewRange(document_id, first, last))
    return found


@router.get("/drafts/{unit_id}")
def get_draft(unit_id: uuid.UUID, user: VerifiedUser, session: DbSession) -> DraftOut:
    try:
        return _out(review.UnitReviewService(session, user.id).get(unit_id))
    except review.UnitNotFound:
        raise _error(404, "unit_not_found") from None


@router.patch("/drafts/{unit_id}")
def edit_draft(
    unit_id: uuid.UUID,
    body: EditIn,
    user: VerifiedUser,
    session: DbSession,
    if_match: Annotated[DbText | None, Header()] = None,
) -> DraftOut:
    version = _version(if_match)
    service = review.UnitReviewService(session, user.id)
    try:
        unit = service.edit(
            unit_id, version, title=body.title, content=body.content, kind=body.kind
        )
    except review.UnitNotFound:
        raise _error(404, "unit_not_found") from None
    except review.UnitChangedElsewhere:
        raise _changed() from None
    except review.NotADraft:
        raise _error(409, "not_a_draft") from None
    return _one(service, unit)


@router.delete("/drafts/{unit_id}")
def discard_draft(unit_id: uuid.UUID, user: VerifiedUser, session: DbSession, now: Now) -> DraftOut:
    service = review.UnitReviewService(session, user.id)
    try:
        unit = service.discard(unit_id, now)
    except review.UnitNotFound:
        raise _error(404, "unit_not_found") from None
    except review.NotADraft:
        raise _error(409, "not_a_draft") from None
    return _one(service, unit)


@router.post("/drafts/{unit_id}/undo")
def undo_discard(unit_id: uuid.UUID, user: VerifiedUser, session: DbSession, now: Now) -> DraftOut:
    service = review.UnitReviewService(session, user.id)
    try:
        unit = service.undo(unit_id, now)
    except review.UnitNotFound:
        raise _error(404, "unit_not_found") from None
    except review.NotUndoable:
        raise _error(409, "not_undoable") from None
    except review.UndoExpired:
        raise _error(410, "undo_expired") from None
    return _one(service, unit)


@router.post("/drafts/{unit_id}/split")
def split_draft(
    unit_id: uuid.UUID,
    body: SplitIn,
    user: VerifiedUser,
    session: DbSession,
    if_match: Annotated[DbText | None, Header()] = None,
) -> DraftsOut:
    version = _version(if_match)
    service = review.UnitReviewService(session, user.id)
    parts = [review.SplitPart(p.title, p.content, tuple(p.anchor_ids)) for p in body.parts]
    try:
        made = service.split(unit_id, version, parts)
    except review.UnitNotFound:
        raise _error(404, "unit_not_found") from None
    except review.UnitChangedElsewhere:
        raise _changed() from None
    except review.NotADraft:
        raise _error(409, "not_a_draft") from None
    except ValueError:
        raise _error(422, "bad_split") from None
    return DraftsOut(drafts=[_out(service.get(u.id)) for u in made], submission_status=None)
