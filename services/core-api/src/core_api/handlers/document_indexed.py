"""`document.indexed.v1` and `document.failed.v1` (T4.8, US-01): ai-service's answer to a
confirmed document.

The consumer has claimed the event (so it is handled once) and checked that every key is under
the event's user; here the document must be that user's too (F2): another user's document id,
or one deleted since, is ignored, as is an answer for a file never confirmed. A repeated answer
for a document (a re-run) replaces the previous one. Logs hold ids, never keys or text
(ADR-0013).
"""

import logging
import uuid

from sqlalchemy.orm import Session

from core_api.db.models import Document
from core_api.db.models.document import UNCONFIRMED
from core_api.messaging.envelope import DocumentFailedEvent, DocumentIndexedEvent, Event
from core_api.repositories.document import DocumentRepository

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


def on_document_indexed(session: Session, event: Event) -> None:
    assert isinstance(event, DocumentIndexedEvent)
    payload = event.payload
    document = _answered(session, event)
    if document is None:
        return
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
        return
    document.status = "indexed"
    document.failure_reason = None
    document.run_id = payload.run_id
    document.page_count = payload.page_count
    document.toc_key = payload.toc_key
    document.page_labels_key = payload.page_labels_key
    document.page_text_key = payload.page_text_key
    document.thumbnails_prefix = payload.thumbnails_prefix
    document.unreadable_pages = sorted(payload.unreadable_pages)


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
