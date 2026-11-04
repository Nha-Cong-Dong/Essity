"""Kho kiến thức (G1, G3, G4): subjects -> study sessions -> the cards a session produced.

A card's text is the ground truth for review (the grader's reference is built from it, see
`core_api.grading.units_of`). Editing writes a `unit_revision` (origin "user"); deleting retires
the card (review history keeps pointing at it, ADR-0008)."""

import json
import re
import uuid
from datetime import date
from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import AfterValidator, BaseModel, Field, StrictStr
from sqlalchemy import ColumnElement, exists, func, or_, select

from core_api.api.deps import Now, Storage, VerifiedUser, verified_user
from core_api.api.text import storable_text
from core_api.clients.storage import StorageUnavailableError
from core_api.db.models import (
    Anchor,
    Document,
    KnowledgeUnit,
    NoteFile,
    StudySession,
    Subject,
    Submission,
    UnitRevision,
)
from core_api.db.session import DbSession

router = APIRouter(prefix="/v1/vault", dependencies=[Depends(verified_user)])

PAGE_TEXT_MAX_BYTES = 8_000_000
READ_URL_SECONDS = 600
MAX_NOTE_IMAGES = 4


class VaultSubjectOut(BaseModel):
    id: uuid.UUID
    name: str
    sessions: int
    cards: int


class VaultSessionOut(BaseModel):
    id: uuid.UUID
    title: str
    studied_on: date | None
    cards: int


class VaultAnchorOut(BaseModel):
    id: uuid.UUID
    source: str
    document_id: uuid.UUID | None
    document_name: str | None
    page_no: int | None
    quote: str


class VaultCardOut(BaseModel):
    id: uuid.UUID
    title: str
    content: str
    kind: str
    anchors: list[VaultAnchorOut]


class VaultCardsOut(BaseModel):
    session_id: uuid.UUID
    title: str
    cards: list[VaultCardOut]


Title = Annotated[StrictStr, Field(min_length=1, max_length=200), AfterValidator(storable_text)]
Body = Annotated[StrictStr, Field(min_length=1, max_length=4000), AfterValidator(storable_text)]


class CardEditIn(BaseModel):
    title: Title | None = None
    content: Body | None = None


class SourceOut(BaseModel):
    anchor_id: uuid.UUID
    source: str
    document_id: uuid.UUID | None
    document_name: str | None
    page_no: int | None
    page_text: str | None  # the extracted text of the page; None for a note or a missing page
    quote: str
    # [start, end) of the quote inside `page_text`; None when it cannot be found there
    highlight: tuple[int, int] | None
    # Short-lived read URLs (G4): the original PDF, and the page's picture (slides, scans).
    file_url: str | None = None
    image_url: str | None = None
    # Photos of the session's notes (a notes source): shown beside the excerpt.
    note_image_urls: list[str] = Field(default_factory=list)


def _error(code: int, detail: str) -> HTTPException:
    return HTTPException(status_code=code, detail=detail)


def session_title(raw: str) -> str:
    lines = raw.strip().splitlines()
    return lines[0][:80] if lines else ""


def _card_clause(user_id: uuid.UUID) -> tuple[ColumnElement[bool], ...]:
    return (
        KnowledgeUnit.user_id == user_id,
        KnowledgeUnit.status == "canonical",
        KnowledgeUnit.session_id.is_not(None),
    )


def _finished_session(user_id: uuid.UUID) -> ColumnElement[bool]:
    """A v1 session confirmed, or a v2 one handed in and processed: a v2 session stays a `draft`
    row for good (`session_result_v2`), its done submission is what finishes it."""
    return or_(
        StudySession.status == "confirmed",
        exists().where(
            Submission.session_id == StudySession.id,
            Submission.user_id == user_id,
            Submission.status == "done",
        ),
    )


@router.get("/subjects")
def vault_subjects(user: VerifiedUser, session: DbSession) -> list[VaultSubjectOut]:
    subjects = session.scalars(
        select(Subject)
        .where(Subject.user_id == user.id, Subject.deleted_at.is_(None))
        .order_by(Subject.created_at)
    ).all()
    sessions = dict(
        session.execute(
            select(StudySession.subject_id, func.count())
            .where(StudySession.user_id == user.id, _finished_session(user.id))
            .group_by(StudySession.subject_id)
        )
        .tuples()
        .all()
    )
    cards = dict(
        session.execute(
            select(KnowledgeUnit.subject_id, func.count())
            .where(*_card_clause(user.id))
            .group_by(KnowledgeUnit.subject_id)
        )
        .tuples()
        .all()
    )
    return [
        VaultSubjectOut(
            id=s.id, name=s.name, sessions=sessions.get(s.id, 0), cards=cards.get(s.id, 0)
        )
        for s in subjects
    ]


@router.get("/subjects/{subject_id}/sessions")
def vault_sessions(
    subject_id: uuid.UUID, user: VerifiedUser, session: DbSession
) -> list[VaultSessionOut]:
    found = session.scalar(
        select(Subject.id).where(
            Subject.id == subject_id, Subject.user_id == user.id, Subject.deleted_at.is_(None)
        )
    )
    if found is None:
        raise _error(status.HTTP_404_NOT_FOUND, "subject_not_found")
    counts = dict(
        session.execute(
            select(KnowledgeUnit.session_id, func.count())
            .where(*_card_clause(user.id), KnowledgeUnit.subject_id == subject_id)
            .group_by(KnowledgeUnit.session_id)
        )
        .tuples()
        .all()
    )
    rows = session.scalars(
        select(StudySession)
        .where(
            StudySession.user_id == user.id,
            StudySession.subject_id == subject_id,
            _finished_session(user.id),
        )
        .order_by(StudySession.studied_on.desc().nulls_last(), StudySession.created_at.desc())
    ).all()
    return [
        VaultSessionOut(
            id=r.id,
            title=session_title(r.description_raw),
            studied_on=r.studied_on,
            cards=counts.get(r.id, 0),
        )
        for r in rows
    ]


def _document_names(
    session: DbSession, user_id: uuid.UUID, ids: set[uuid.UUID]
) -> dict[uuid.UUID, str]:
    if not ids:
        return {}
    return dict(
        session.execute(
            select(Document.id, Document.short_name).where(
                Document.user_id == user_id, Document.id.in_(ids)
            )
        )
        .tuples()
        .all()
    )


def _anchor_out(a: Anchor, names: dict[uuid.UUID, str]) -> VaultAnchorOut:
    return VaultAnchorOut(
        id=a.id,
        source=a.source,
        document_id=a.document_id,
        document_name=names.get(a.document_id) if a.document_id else None,
        page_no=a.page_no,
        quote=a.quote_text,
    )


@router.get("/sessions/{session_id}/cards")
def vault_cards(session_id: uuid.UUID, user: VerifiedUser, session: DbSession) -> VaultCardsOut:
    study = session.scalar(
        select(StudySession).where(StudySession.id == session_id, StudySession.user_id == user.id)
    )
    if study is None:
        raise _error(status.HTTP_404_NOT_FOUND, "session_not_found")
    units = session.scalars(
        select(KnowledgeUnit)
        .where(*_card_clause(user.id), KnowledgeUnit.session_id == session_id)
        .order_by(KnowledgeUnit.created_at, KnowledgeUnit.id)
    ).all()
    anchors = session.scalars(
        select(Anchor)
        .where(Anchor.user_id == user.id, Anchor.unit_id.in_([u.id for u in units]))
        .order_by(Anchor.created_at, Anchor.id)
    ).all()
    names = _document_names(session, user.id, {a.document_id for a in anchors if a.document_id})
    by_unit: dict[uuid.UUID, list[VaultAnchorOut]] = {}
    for a in anchors:
        by_unit.setdefault(a.unit_id, []).append(_anchor_out(a, names))
    return VaultCardsOut(
        session_id=session_id,
        title=session_title(study.description_raw),
        cards=[
            VaultCardOut(
                id=u.id,
                title=u.title,
                content=u.summary,
                kind=u.kind,
                anchors=by_unit.get(u.id, []),
            )
            for u in units
        ],
    )


def _own_card(session: DbSession, user_id: uuid.UUID, card_id: uuid.UUID) -> KnowledgeUnit:
    unit = session.scalar(
        select(KnowledgeUnit)
        .where(KnowledgeUnit.id == card_id, KnowledgeUnit.user_id == user_id)
        .with_for_update()
    )
    if unit is None or unit.status != "canonical":
        raise _error(status.HTTP_404_NOT_FOUND, "card_not_found")
    return unit


@router.patch("/cards/{card_id}")
def edit_card(
    card_id: uuid.UUID, body: CardEditIn, user: VerifiedUser, session: DbSession
) -> VaultCardOut:
    """ "Lưu" on the card: the new text is the answer reviews compare against."""
    unit = _own_card(session, user.id, card_id)
    title = (body.title if body.title is not None else unit.title).strip()
    content = (body.content if body.content is not None else unit.summary).strip()
    if not title or not content:
        raise _error(status.HTTP_422_UNPROCESSABLE_ENTITY, "blank")
    if (title, content) != (unit.title, unit.summary):
        unit.title = title
        unit.summary = content
        rev = session.scalar(
            select(func.coalesce(func.max(UnitRevision.rev), -1)).where(
                UnitRevision.unit_id == unit.id
            )
        )
        session.add(
            UnitRevision(
                user_id=user.id,
                unit_id=unit.id,
                rev=(-1 if rev is None else rev) + 1,
                origin="user",
                content={"title": title, "content": content, "kind": unit.kind},
            )
        )
        session.flush()
    anchors = session.scalars(
        select(Anchor).where(Anchor.user_id == user.id, Anchor.unit_id == unit.id)
    ).all()
    names = _document_names(session, user.id, {a.document_id for a in anchors if a.document_id})
    return VaultCardOut(
        id=unit.id,
        title=unit.title,
        content=unit.summary,
        kind=unit.kind,
        anchors=[_anchor_out(a, names) for a in anchors],
    )


@router.delete("/cards/{card_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_card(card_id: uuid.UUID, user: VerifiedUser, session: DbSession, now: Now) -> Response:
    unit = _own_card(session, user.id, card_id)
    unit.status = "retired"
    unit.retired_at = now
    session.flush()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _page_text(storage: Storage, document: Document, page_no: int) -> str | None:
    if document.page_text_key is None:
        return None
    try:
        raw = storage.read(document.page_text_key, max_bytes=PAGE_TEXT_MAX_BYTES)
    except StorageUnavailableError:
        return None
    if raw is None:
        return None
    try:
        pages: object = json.loads(raw).get("pages")
    except (ValueError, AttributeError):
        return None
    if not isinstance(pages, list):
        return None
    for page in cast(list[Any], pages):
        if isinstance(page, dict):
            entry = cast(dict[str, Any], page)
            if entry.get("page") == page_no:
                text = entry.get("text")
                return text if isinstance(text, str) else None
    return None


def find_highlight(page_text: str, quote: str) -> tuple[int, int] | None:
    """Where `quote` sits in `page_text`: exact first, then ignoring runs of whitespace."""
    at = page_text.find(quote)
    if at >= 0:
        return at, at + len(quote)
    words = quote.split()
    if not words:
        return None
    match = re.search(r"\s+".join(re.escape(w) for w in words), page_text)
    return (match.start(), match.end()) if match else None


@router.get("/cards/{card_id}/sources")
def card_sources(
    card_id: uuid.UUID, user: VerifiedUser, session: DbSession, storage: Storage
) -> list[SourceOut]:
    """ "Nguồn" on the card: for each anchor the page's extracted text with the cited passage's
    position, so the screen can mark it (a real PDF highlight is for later)."""
    unit = _own_card(session, user.id, card_id)
    anchors = session.scalars(
        select(Anchor)
        .where(Anchor.user_id == user.id, Anchor.unit_id == card_id)
        .order_by(Anchor.created_at, Anchor.id)
    ).all()
    document_ids = [a.document_id for a in anchors if a.document_id]
    documents = {
        d.id: d
        for d in session.scalars(
            select(Document).where(Document.user_id == user.id, Document.id.in_(document_ids))
        )
    }
    out: list[SourceOut] = []

    def presign(key: str | None) -> str | None:
        if key is None:
            return None
        try:
            return storage.presign_get(key, expires_in=READ_URL_SECONDS)
        except Exception:  # noqa: BLE001 - the screen falls back to the page text
            return None

    note_keys: list[str] = []
    if unit.session_id is not None and any(a.source == "notes" for a in anchors):
        note_keys = list(
            session.scalars(
                select(NoteFile.object_key)
                .where(
                    NoteFile.user_id == user.id,
                    NoteFile.session_id == unit.session_id,
                    NoteFile.mime.like("image/%"),
                )
                .order_by(NoteFile.created_at)
                .limit(MAX_NOTE_IMAGES)
            )
        )
    note_urls = [u for u in (presign(k) for k in note_keys) if u is not None]
    for a in anchors:
        document = documents.get(a.document_id) if a.document_id else None
        text = (
            _page_text(storage, document, a.page_no)
            if document is not None and a.page_no is not None
            else None
        )
        out.append(
            SourceOut(
                anchor_id=a.id,
                source=a.source,
                document_id=a.document_id,
                document_name=document.short_name if document else None,
                page_no=a.page_no,
                page_text=text,
                quote=a.quote_text,
                highlight=find_highlight(text, a.quote_text) if text else None,
                file_url=presign(document.object_key)
                if document is not None and document.format == "pdf"
                else None,
                note_image_urls=note_urls if a.source == "notes" else [],
                image_url=presign(f"{document.thumbnails_prefix}/{a.page_no}.png")
                if document is not None and document.thumbnails_prefix and a.page_no
                else None,
            )
        )
    return out
