"""`document.indexed.v1` and `document.failed.v1` (T4.8, US-01): ai-service's answer to a
confirmed document.

The consumer has claimed the event (so it is handled once) and checked that every key is under
the event's user; here the document must be that user's too (F2): another user's document id,
or one deleted since, is ignored, as is an answer for a file never confirmed. A repeated answer
for a document (a re-run) replaces the previous one. Logs hold ids, never keys or text
(ADR-0013).

T7.4: `OnDocumentIndexed` also reads the outline ai-service wrote beside the other derived files
(`outline.json`, same prefix: no event field names it) and stores it as the document's
`doc_section` tree. A missing or broken file leaves the document indexed with no outline; the
storage not answering raises, and the consumer retries. See `services.outline.store_outline`
for what a repeated answer does to an outline the learner has touched.
"""

import logging
import uuid
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.orm import Session

from core_api.clients.storage import ObjectStorage
from core_api.db.models import Document
from core_api.db.models.document import UNCONFIRMED
from core_api.messaging.envelope import DocumentFailedEvent, DocumentIndexedEvent, Event
from core_api.repositories.doc_section import NewSection
from core_api.repositories.document import DocumentRepository
from core_api.services.outline import OutlineService

_log = logging.getLogger("core_api.handlers")


def _answered(
    session: Session, event: DocumentIndexedEvent | DocumentFailedEvent
) -> Document | None:
    document = DocumentRepository(session, event.user_id).lock(event.payload.document_id)
    if document is None or document.status in UNCONFIRMED:
        _log.warning(
            "document answer ignored",
            extra={
                "event_id": str(event.event_id),
                "document_id": str(event.payload.document_id),
                "found": document is not None,
            },
        )
        return None
    return document


def _derived(document: Document, run_id: uuid.UUID) -> str:
    return f"users/{document.user_id}/subjects/{document.subject_id}/derived/{run_id}/"


# ai-service's own cap: a book of a few thousand pages has a few hundred sections.
MAX_OUTLINE_BYTES = 2_000_000
MAX_SECTIONS = 2000
OUTLINE_NAME = "outline.json"


def _no_nul(text: str) -> str:
    if "\x00" in text:
        raise ValueError("NUL")
    return text


def _not_blank(text: str) -> str:
    if not text.strip():
        raise ValueError("blank")
    return text


class _OutlineNode(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    title: Annotated[
        str, AfterValidator(_no_nul), AfterValidator(_not_blank), Field(max_length=300)
    ]
    parent: Annotated[int, Field(ge=0)] | None
    page_start: Annotated[int, Field(ge=1, le=100_000)]
    page_end: Annotated[int, Field(ge=1, le=100_000)]
    weight: Annotated[float, Field(ge=0, allow_inf_nan=False)]
    source: Literal["bookmark", "heading", "llm_toc", "chunk10"]


class _OutlineFile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    unit: Literal["page", "slide", "est_page"]
    nodes: Annotated[list[_OutlineNode], Field(min_length=1, max_length=MAX_SECTIONS)]


def parse_outline(raw: bytes, page_count: int) -> tuple[str, list[NewSection]] | None:
    """The unit and sections of `outline.json`, or None when the file breaks a rule: it is
    ai-service's, but a section pointing outside the file or its parent would corrupt progress."""
    try:
        parsed = _OutlineFile.model_validate_json(raw)
    except ValidationError:  # its errors echo the input: never logged
        return None
    nodes = parsed.nodes
    for index, node in enumerate(nodes):
        if node.page_end < node.page_start:
            return None
        if parsed.unit == "page" and node.page_end > page_count:
            return None
        if node.parent is not None:
            if node.parent >= index:
                return None
            above = nodes[node.parent]
            if node.page_start < above.page_start or node.page_end > above.page_end:
                return None
    return parsed.unit, [
        NewSection(
            title=n.title.strip(),
            parent=n.parent,
            first_page=n.page_start,
            last_page=n.page_end,
            weight=n.weight,
            unit=parsed.unit,
            source=n.source,
        )
        for n in nodes
    ]


def on_document_indexed(session: Session, event: Event) -> None:
    """The document's state only (T4.8); `OnDocumentIndexed` adds the outline."""
    _apply_indexed(session, event)


def _apply_indexed(session: Session, event: Event) -> Document | None:
    assert isinstance(event, DocumentIndexedEvent)
    payload = event.payload
    document = _answered(session, event)
    if document is None:
        return None
    keys = (
        payload.toc_key,
        payload.page_labels_key,
        payload.page_text_key,
        payload.thumbnails_prefix,
    )
    prefix = _derived(document, payload.run_id)
    if not all(key.startswith(prefix) for key in keys) or any(
        page > payload.page_count for page in payload.unreadable_pages
    ):
        _log.warning(
            "document answer refused",
            extra={"event_id": str(event.event_id), "document_id": str(document.id)},
        )
        return None
    document.status = "indexed"
    document.failure_reason = None
    document.run_id = payload.run_id
    document.page_count = payload.page_count
    document.toc_key = payload.toc_key
    document.page_labels_key = payload.page_labels_key
    document.page_text_key = payload.page_text_key
    document.thumbnails_prefix = payload.thumbnails_prefix
    document.unreadable_pages = sorted(payload.unreadable_pages)
    return document


class OnDocumentIndexed:
    def __init__(self, storage: ObjectStorage) -> None:
        self.storage = storage

    def __call__(self, session: Session, event: Event) -> None:
        assert isinstance(event, DocumentIndexedEvent)
        document = _apply_indexed(session, event)
        if document is None or document.toc_key is None or document.page_count is None:
            return
        extra = {"event_id": str(event.event_id), "document_id": str(document.id)}
        key = document.toc_key.rsplit("/", 1)[0] + "/" + OUTLINE_NAME
        raw = self.storage.read(key, max_bytes=MAX_OUTLINE_BYTES)  # raises: retried
        parsed = None if raw is None else parse_outline(raw, document.page_count)
        if parsed is None:
            _log.warning("document outline missing or refused", extra=extra)
            return
        stored = OutlineService(session, document.user_id).store_outline(document, parsed[1])
        _log.info("document outline stored", extra=extra | {"stored": stored})


def on_document_failed(session: Session, event: Event) -> None:
    assert isinstance(event, DocumentFailedEvent)
    payload = event.payload
    document = _answered(session, event)
    if document is None:
        return
    document.status = "failed"
    document.failure_reason = payload.reason
    document.run_id = payload.run_id
    document.page_count = None
    document.toc_key = document.page_labels_key = document.page_text_key = None
    document.thumbnails_prefix = None
    document.unreadable_pages = sorted(payload.unreadable_pages)
