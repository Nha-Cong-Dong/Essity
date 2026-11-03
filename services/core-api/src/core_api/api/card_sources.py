"""`GET /v1/units/{id}/sources` (G4): where a card came from, for the "Nguồn" view.

One item per anchor of the card: the document, the page, the cited passage and the extracted text
of that page with the passage located in it (`mark_start`..`mark_end`, characters of `page_text`).
A note anchor has no page text. The page text is the file ai-service wrote when it indexed the
document; when it is missing the item still carries the quote. Nothing is logged but ids."""

import json
import re
import uuid
from typing import Any, cast

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy import select

from core_api.api.deps import Storage, VerifiedUser, verified_user
from core_api.clients.storage import StorageUnavailableError
from core_api.db.models import Anchor, Document
from core_api.db.session import DbSession
from core_api.repositories.subject import SubjectRepository
from core_api.repositories.unit import KnowledgeUnitRepository

router = APIRouter(prefix="/v1", dependencies=[Depends(verified_user)])

_MAX_PAGES_BYTES = 20_000_000
_PAGE_TEXT_MAX = 50_000


class CardSourceOut(BaseModel):
    anchor_id: uuid.UUID
    document_id: uuid.UUID | None  # None: a note
    document_name: str | None
    subject_id: uuid.UUID
    page_no: int | None
    quote: str
    page_text: str | None  # extracted text of that page, None when it cannot be read
    mark_start: int | None  # the quote in page_text, None when it is not found there
    mark_end: int | None


class CardSourcesOut(BaseModel):
    unit_id: uuid.UUID
    title: str
    sources: list[CardSourceOut]


def locate(
    text: str, quote: str, char_start: int | None, char_end: int | None
) -> tuple[int, int] | None:
    """The quote inside the page text: the stored range when it still reads the quote, else the
    first exact match, else a match that ignores differences in whitespace."""
    if char_start is not None and char_end is not None and text[char_start:char_end] == quote:
        return char_start, char_end
    at = text.find(quote)
    if at >= 0:
        return at, at + len(quote)
    words = quote.split()
    if not words:
        return None
    pattern = r"\s+".join(re.escape(w) for w in words)
    found = re.search(pattern, text)
    return (found.start(), found.end()) if found else None


def _pages(storage: Storage, document: Document) -> list[str] | None:
    if document.page_text_key is None:
        return None
    try:
        raw = storage.read_start(document.page_text_key, _MAX_PAGES_BYTES + 1)
    except StorageUnavailableError:
        return None
    if len(raw) > _MAX_PAGES_BYTES:
        return None
    try:
        data: Any = json.loads(raw)
    except ValueError:
        return None
    items: Any = cast("dict[str, Any]", data).get("pages") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return None
    texts: list[str] = []
    for item in cast("list[Any]", items):
        text = cast("dict[str, Any]", item).get("text") if isinstance(item, dict) else None
        texts.append(text if isinstance(text, str) else "")
    return texts


@router.get("/units/{unit_id}/sources", response_model=CardSourcesOut)
def card_sources(
    unit_id: uuid.UUID,
    user: VerifiedUser,
    session: DbSession,
    storage: Storage,
    response: Response,
) -> CardSourcesOut:
    """Errors: 404 `unit_not_found` (another user's, or its subject was deleted)."""
    response.headers["Cache-Control"] = "no-store"
    unit = KnowledgeUnitRepository(session, user.id).get(unit_id)
    if unit is None or SubjectRepository(session, user.id).get(unit.subject_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unit_not_found")
    anchors = session.scalars(
        select(Anchor)
        .where(Anchor.user_id == user.id, Anchor.unit_id == unit.id)
        .order_by(Anchor.created_at, Anchor.id)
    ).all()
    document_ids = {a.document_id for a in anchors if a.document_id is not None}
    documents = {
        d.id: d
        for d in session.scalars(
            select(Document).where(Document.user_id == user.id, Document.id.in_(document_ids))
        )
    }
    pages: dict[uuid.UUID, list[str] | None] = {}
    out: list[CardSourceOut] = []
    for a in anchors:
        document = documents.get(a.document_id) if a.document_id is not None else None
        text: str | None = None
        if document is not None and a.page_no is not None:
            if document.id not in pages:
                pages[document.id] = _pages(storage, document)
            texts = pages[document.id]
            if texts is not None and 1 <= a.page_no <= len(texts):
                text = texts[a.page_no - 1][:_PAGE_TEXT_MAX]
        span = locate(text, a.quote_text, a.char_start, a.char_end) if text is not None else None
        out.append(
            CardSourceOut(
                anchor_id=a.id,
                document_id=document.id if document else None,
                document_name=document.short_name if document else None,
                subject_id=unit.subject_id,
                page_no=a.page_no,
                quote=a.quote_text,
                page_text=text,
                mark_start=span[0] if span else None,
                mark_end=span[1] if span else None,
            )
        )
    return CardSourcesOut(unit_id=unit.id, title=unit.title, sources=out)
