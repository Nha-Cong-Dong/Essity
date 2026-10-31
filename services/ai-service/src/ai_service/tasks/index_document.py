"""Index an uploaded PDF (T4.7): `document.uploaded.v1` in, derived files and `document.indexed.v1`
(or `document.failed.v1`) out.

The file is read in a child process of its own, one at a time (ADR-0011: PDFium is not thread
safe, and a crash or a loop inside it must end that process, not the worker). A fresh child
serves every file, so a heap that `malformed` left damaged is never reused.

Idempotent on the event (consumer.Handler): the run id and the id of the event sent are derived
from the incoming event's id, so a second handling writes the same keys and sends the same event,
which core-api's own claim drops. Nothing here logs a document's name, key or text.

Deferred, not failed: the storage not answering. Failed (an event, not an exception): everything
about the file itself, because asking again gives the same answer. A bug in this code raises, and
the consumer counts it towards the dead letter.
"""

import hashlib
import json
import multiprocessing
import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from redis import Redis
from sqlalchemy.orm import Session

from ai_service.clients.storage import (
    ObjectNotFound,
    ObjectStorage,
    ObjectTooLarge,
    StorageUnavailable,
)
from ai_service.db.session import SessionFactory
from ai_service.llm.client import LlmClient
from ai_service.messaging.consumer import Deferred, keys_belong_to_user
from ai_service.messaging.dead_letter import STREAM_MAXLEN
from ai_service.messaging.envelope import (
    DocumentFailed,
    DocumentFailedEvent,
    DocumentIndexed,
    DocumentIndexedEvent,
    DocumentUploadedEvent,
    Event,
    dump_event,
)
from ai_service.pdf import OutlineEntry, PageText, PdfError, PdfErrorCode, PdfLimits, open_pdf
from ai_service.tasks.syllabus import SyllabusAsker, SyllabusPrompt, build_syllabus, outline_file

OUT_STREAM = "events.ai"
THUMBNAIL_PX = 400
# The longest the child may take: the library's own deadline (120 s) for the reads, plus the
# time to render and send back the thumbnails.
CHILD_TIMEOUT_S = 180.0
# Address space of the child; a PDF that needs more is refused rather than starving the host.
_CHILD_MEMORY_BYTES = 4 * 1024**3

_RAW_KEY = re.compile(r"/raw/([0-9a-f]{64})\.([A-Za-z0-9]+)$")
_NAMESPACE = uuid.UUID("5b1b6f0e-8c0e-4e5a-9a37-7a0e6d6f1c11")


@dataclass(frozen=True)
class Analysis:
    page_count: int
    outline: list[OutlineEntry]
    page_labels: list[str] | None
    pages: list[PageText]
    thumbnails: list[bytes]


def run_id_for(event_id: uuid.UUID) -> uuid.UUID:
    return uuid.uuid5(_NAMESPACE, f"run:{event_id}")


def indexed_event_id(event_id: uuid.UUID) -> uuid.UUID:
    return uuid.uuid5(_NAMESPACE, f"indexed:{event_id}")


def pointer_key(subject_prefix: str, document_id: uuid.UUID) -> str:
    """`users/<u>/subjects/<s>/documents/<document>/index.json`: the latest index of a document."""
    return f"{subject_prefix}/documents/{document_id}/index.json"


def failed_event_id(event_id: uuid.UUID) -> uuid.UUID:
    return uuid.uuid5(_NAMESPACE, f"failed:{event_id}")


def analyze(data: bytes, limits: PdfLimits) -> Analysis:
    """Everything read from one PDF. Runs in the child. Raises PdfError."""
    with open_pdf(data, limits=limits) as pdf:
        count = pdf.page_count
        outline = pdf.get_outline()
        labels = pdf.get_page_labels()
        pages = [pdf.extract_text(index) for index in range(count)]
        thumbnails = [pdf.render_page(index, max_px=THUMBNAIL_PX).png for index in range(count)]
    return Analysis(count, outline, labels, pages, thumbnails)


Target = Callable[[bytes, PdfLimits], Analysis]


def _child(conn: Any, target: Target, data: bytes, limits: PdfLimits) -> None:
    try:
        import resource  # POSIX only; the containers run Linux

        limits_api: Any = resource
        limits_api.setrlimit(limits_api.RLIMIT_AS, (_CHILD_MEMORY_BYTES, _CHILD_MEMORY_BYTES))
    except (ImportError, ValueError, OSError):
        pass
    try:
        conn.send(("ok", target(data, limits)))
    except PdfError as error:
        conn.send(("pdf", error.code))
    except MemoryError:
        conn.send(("pdf", "too_large"))
    except Exception as error:  # a bug: the type only, never a message that may hold text
        conn.send(("bug", type(error).__name__))
    finally:
        conn.close()


def run_isolated(
    data: bytes,
    limits: PdfLimits,
    *,
    timeout_s: float = CHILD_TIMEOUT_S,
    target: Target = analyze,
) -> Analysis:
    """`target(data, limits)` in a fresh child process. Raises PdfError: the child's own, or
    `malformed` when it died without answering and `deadline` when it was killed for time."""
    context = multiprocessing.get_context("spawn")
    receiver, sender = context.Pipe(duplex=False)
    process = context.Process(target=_child, args=(sender, target, data, limits), daemon=True)
    process.start()
    sender.close()
    try:
        if not receiver.poll(timeout_s):
            raise PdfError("deadline")
        try:
            kind, value = receiver.recv()
        except (EOFError, OSError):
            raise PdfError("malformed") from None
    finally:
        receiver.close()
        if process.is_alive():
            process.kill()
        process.join(10)
        process.close()
    if kind == "ok":
        return value
    if kind == "pdf":
        raise PdfError(value)
    raise RuntimeError(f"document analysis failed: {value}")


_FAILURE: dict[PdfErrorCode, str] = {
    "too_large": "too_large",
    "too_many_pages": "too_large",
    "encrypted": "unsupported",
    "malformed": "unreadable",
    "deadline": "unreadable",
    "page_out_of_range": "internal_error",
    "closed": "internal_error",
}


OUTLINE_NAME = "outline.json"


def _no_model(prompt: SyllabusPrompt) -> str:
    raise RuntimeError("no model")


def _json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


class IndexDocument:
    """The handler of `document.uploaded.v1`."""

    def __init__(
        self,
        *,
        storage: ObjectStorage,
        redis: Redis,
        stream: str = OUT_STREAM,
        limits: PdfLimits | None = None,
        analyze: Target = run_isolated,
        llm: LlmClient | None = None,
        sessions: SessionFactory | None = None,
    ) -> None:
        self.llm = llm
        self.sessions = sessions
        self.storage = storage
        self.redis = redis
        self.stream = stream
        self.limits = limits or PdfLimits()
        self.analyze = analyze

    def __call__(self, session: Session, event: Event) -> None:
        if not isinstance(event, DocumentUploadedEvent):
            raise TypeError("IndexDocument handles document.uploaded.v1 only")
        payload = event.payload
        run_id = run_id_for(event.event_id)

        def fail(reason: str) -> None:
            self._send(
                DocumentFailedEvent(
                    event_id=failed_event_id(event.event_id),
                    event_type="document.failed.v1",
                    schema_version=1,
                    occurred_at=datetime.now(UTC),
                    user_id=event.user_id,
                    trace_context=event.trace_context,
                    payload=DocumentFailed(
                        document_id=payload.document_id,
                        run_id=run_id,
                        reason=reason,  # pyright: ignore[reportArgumentType]
                        unreadable_pages=[],
                    ),
                )
            )

        # F2 again (the consumer already dead-letters it): a key outside the event's user is
        # refused before the storage is touched.
        if not keys_belong_to_user(event):
            return fail("unsupported")
        named = _RAW_KEY.search(payload.object_key)
        if named is None or named.group(2) != "pdf":
            return fail("unsupported")
        try:
            data = self.storage.get(payload.object_key, max_bytes=self.limits.max_bytes)
        except ObjectNotFound:
            return fail("unreadable")
        except ObjectTooLarge:
            return fail("too_large")
        except StorageUnavailable:
            raise Deferred from None
        # The storage may not check the checksum the uploader promised (PLAN T4.5 risk).
        if hashlib.sha256(data).hexdigest() != named.group(1):
            return fail("unreadable")
        try:
            analysis = self.analyze(data, self.limits)
        except PdfError as error:
            return fail(_FAILURE[error.code])

        prefix = payload.object_key[: named.start()] + f"/derived/{run_id}"
        keys = DocumentIndexed(
            document_id=payload.document_id,
            run_id=run_id,
            page_count=analysis.page_count,
            toc_key=f"{prefix}/toc.json",
            page_labels_key=f"{prefix}/page_labels.json",
            page_text_key=f"{prefix}/page_text.json",
            thumbnails_prefix=f"{prefix}/thumbnails",
            unreadable_pages=[n for n, page in enumerate(analysis.pages, 1) if page.needs_vision],
        )
        try:
            self._write(
                keys,
                analysis,
                payload.object_key[: named.start()],
                payload.document_id,
                self._outline(analysis, event.user_id, payload.subject_id),
            )
        except StorageUnavailable:
            raise Deferred from None
        self._send(
            DocumentIndexedEvent(
                event_id=indexed_event_id(event.event_id),
                event_type="document.indexed.v1",
                schema_version=1,
                occurred_at=datetime.now(UTC),
                user_id=event.user_id,
                trace_context=event.trace_context,
                payload=keys,
            )
        )

    def _write(
        self,
        keys: DocumentIndexed,
        analysis: Analysis,
        subject_prefix: str,
        document_id: uuid.UUID,
        outline: dict[str, Any],
    ) -> None:
        put = self.storage.put
        json_type = "application/json"
        toc = [
            {
                "title": entry.title,
                "level": entry.level,
                "page": None if entry.page_index is None else entry.page_index + 1,
            }
            for entry in analysis.outline
        ]
        pages = [
            {"page": number, "text": page.text, "needs_vision": page.needs_vision}
            for number, page in enumerate(analysis.pages, 1)
        ]
        put(keys.toc_key, _json({"entries": toc}), content_type=json_type)
        put(keys.page_labels_key, _json({"labels": analysis.page_labels}), content_type=json_type)
        # core-api reads it beside the other derived files (T7.4); no event field names it.
        put(
            f"{keys.toc_key.rsplit('/', 1)[0]}/{OUTLINE_NAME}",
            _json(outline),
            content_type=json_type,
        )
        put(keys.page_text_key, _json({"pages": pages}), content_type=json_type)
        # Written last among the text files: session.confirmed.v1 names a document by id only
        # (T4.16b), and this is where process_session finds the page text of its latest index.
        put(
            pointer_key(subject_prefix, document_id),
            _json({"page_text_key": keys.page_text_key, "page_count": keys.page_count}),
            content_type=json_type,
        )
        for number, png in enumerate(analysis.thumbnails, 1):
            put(f"{keys.thumbnails_prefix}/{number}.png", png, content_type="image/png")

    def _outline(
        self, analysis: Analysis, user_id: uuid.UUID, subject_id: uuid.UUID
    ) -> dict[str, Any]:
        """The syllabus of the file (T7.4, US-13 AC2-3): bookmarks and headings cost nothing; the
        model reads contents pages only when there are no bookmarks and no chapter headings. With
        no model (disabled, or no database to audit in) the tree falls through to blocks of 10."""
        asker: SyllabusAsker | None = None
        ask = _no_model
        if self.llm is not None and self.sessions is not None:
            asker = SyllabusAsker(self.llm, self.sessions, user_id=user_id, subject_id=subject_id)
            ask = asker
        try:
            nodes = build_syllabus(analysis.page_count, analysis.outline, analysis.pages, ask)
        finally:
            if asker is not None:
                asker.finish()
        return outline_file(nodes)

    def _send(self, event: Event) -> None:
        self.redis.xadd(
            self.stream,
            {"envelope": dump_event(event)},
            maxlen=STREAM_MAXLEN,
            approximate=True,
        )
