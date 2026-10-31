"""Process a learner's submission (T7.7, US-02/US-02b): `submission.created.v1` in, a
`session-result.v2` file and `submission.processed.v1` out (`submission.failed.v1` when it cannot
be done).

What it does, in order: reads the context core-api wrote (mentions resolved at submit time, the
learner's description), the page text of the mentioned ranges (through the pointer the indexer
writes, T4.7) and the submitted files; reads notes images and scanned PDF pages by vision
(`read_notes_image`, capped, cached by image hash); splits everything into batches; asks
`draft_units` for each batch; merges drafts that share a `draft_key`; and writes the result
file, checked against its own contract copy before it is stored. core-api turns the drafts into
cards the learner reviews (T7.8). Nothing here writes to a database of core (ADR-0002).

Idempotent on the event (consumer.Handler) and cached per submission: the result file is
`result-<submission_id>.json`, so a job delivered again, even as a new event, finds it and only
announces it again; each batch's drafts and each image's reading are kept in the user's `derived/`
prefix, so a retry after a failure in the middle pays for nothing twice. The ids of the events
sent derive from the incoming event's id: a new `submission.created` for the same submission
(after `llm_unavailable`) gets new ids and is not mistaken for a repeat.

The AI cost cap is not a hard error: it ends as `submission.failed(llm_unavailable)`, which core
treats as `pending_ai` and retries (decision D1 of the T7.7 plan); nothing is cached then.

Nothing here logs page text, notes, a description or model output (ADR-0013): rule names and
counts only. Anything read from a file or an image is untrusted text and reaches a prompt only
through `draft_units` (escaped data blocks).
"""

import dataclasses
import hashlib
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from pydantic import TypeAdapter, ValidationError
from redis import Redis
from sqlalchemy import func, update
from sqlalchemy.orm import Session

from ai_service.clients.storage import (
    ObjectNotFound,
    ObjectStorage,
    ObjectTooLarge,
    StorageUnavailable,
)
from ai_service.db.models import PipelineRun
from ai_service.db.session import SessionFactory
from ai_service.docx.python_docx_impl import read_docx
from ai_service.llm.client import AuditUnavailableError, LlmClient, LlmUnavailableError
from ai_service.llm.quota import QuotaExceededError
from ai_service.llm.types import LlmRequest, Task
from ai_service.messaging.consumer import Deferred
from ai_service.messaging.dead_letter import STREAM_MAXLEN
from ai_service.messaging.envelope import (
    Event,
    SubmissionCreatedEvent,
    SubmissionFailed,
    SubmissionFailedEvent,
    SubmissionProcessed,
    SubmissionProcessedEvent,
    dump_event,
)
from ai_service.messaging.session_result_v2 import (
    Anchor as WireAnchor,
)
from ai_service.messaging.session_result_v2 import (
    Draft as WireDraft,
)
from ai_service.messaging.session_result_v2 import (
    Dropped as WireDropped,
)
from ai_service.messaging.session_result_v2 import (
    SessionResultV2,
    Skipped,
)
from ai_service.messaging.submission_context import SubmissionContext, parse_context
from ai_service.pdf.pdfium_impl import open_pdf
from ai_service.pdf.types import PdfError
from ai_service.pptx.python_pptx_impl import read_pptx
from ai_service.tasks import draft_units as draft_task
from ai_service.tasks import read_notes_image as read_task
from ai_service.tasks.chunk_units import (
    MAX_NOTES_CHARS,
    MAX_PAGE_CHARS,
    MAX_PAGES,
    ChunkInputError,
    ChunkInvalidError,
    ChunkPrompt,
    Prompt,
)
from ai_service.tasks.draft_units import (
    Draft,
    DraftAnchor,
    DraftOutcome,
    DraftRequest,
    ScopedDoc,
    ScopedPage,
    draft_units,
    to_chunk_request,
)
from ai_service.tasks.read_notes_image import ImageSource, ReadPrompt, read_images

OUT_STREAM = "events.ai"
_NAMESPACE = uuid.UUID("5b8f2c1e-7d34-4e0a-9a61-0c2f4d8e1b73")
_JSON = "application/json"

MAX_INDEX_BYTES = 20_000_000
MAX_POINTER_BYTES = 20_000
MAX_CONTEXT_BYTES = 1_000_000
MAX_FILE_BYTES = 30_000_000
MAX_RESULT_BYTES = 8_000_000
MAX_CACHED_BYTES = 2_000_000
BATCH_PAGES = 20
BATCH_CHARS = 100_000
# Pages of documents read for one submission (decision D4/O2): the rest is `truncated`.
MAX_SCOPE_PAGES = MAX_PAGES
# Characters of the learner's own submitted text read in all, before the rest is `truncated`.
MAX_NOTES_TOTAL_CHARS = 5 * MAX_NOTES_CHARS
MAX_DRAFTS = 200
CALL_SECONDS = 90.0
RENDER_PX = 1400
TEXT_MIMES = frozenset({"text/plain", "text/markdown"})
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
PPTX = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
IMAGE_MIMES = frozenset({"image/jpeg", "image/png"})

_log = logging.getLogger(__name__)
_DRAFTS = TypeAdapter(list[Draft])


def run_id_for(event_id: uuid.UUID) -> uuid.UUID:
    return uuid.uuid5(_NAMESPACE, f"run:{event_id}")


def result_key_for(event: SubmissionCreatedEvent) -> str:
    """`users/<user>/sessions/<session>/result-<submission>.json`: one per submission, not per
    event, so a job delivered again finds what the first one paid for."""
    payload = event.payload
    session = f"users/{event.user_id}/sessions/{payload.study_session_id}"
    return f"{session}/result-{payload.submission_id}.json"


class _Fail(Exception):
    def __init__(self, reason: str, code: str) -> None:
        super().__init__(code)
        self.reason, self.code = reason, code


@dataclass
class _Work:
    """What one run collects. `skipped` holds a kind, a number and a fixed reason, never text."""

    skipped: list[Skipped] = field(default_factory=lambda: list[Skipped]())
    dropped_anchors: int = 0
    dropped_drafts: int = 0

    def skip(self, kind: str, ref: int, reason: str) -> None:
        item = Skipped(kind=kind, ref=ref, reason=reason)  # type: ignore[arg-type]
        if item not in self.skipped:  # one neutral note, however many places found the same
            self.skipped.append(item)


@dataclass
class _Page:
    document_id: uuid.UUID
    number: int
    text: str
    section_ids: list[uuid.UUID]


@dataclass
class _Batch:
    pages: list[_Page]
    notes: str | None
    notes_offset: int


class StorageVisionCache:
    """What a notes image says, kept under the user's own `derived/` prefix (ADR-0012), not in
    Redis: the text of a learner's notes must not outlive their account, and the cache must
    answer when the same image comes back next week. Deleting the account deletes the prefix."""

    def __init__(self, storage: ObjectStorage, user_id: uuid.UUID) -> None:
        self._storage, self._prefix = storage, f"users/{user_id}/derived/vision/"

    def get(self, key: str) -> str | None:
        try:
            raw = self._storage.get(f"{self._prefix}{key}.json", max_bytes=MAX_CACHED_BYTES)
            text = json.loads(raw)["text"]
        except (ObjectNotFound, ObjectTooLarge, ValueError, KeyError, TypeError):
            return None
        except StorageUnavailable:
            raise Deferred from None
        return text if isinstance(text, str) else None

    def put(self, key: str, text: str) -> None:
        try:
            self._storage.put(
                f"{self._prefix}{key}.json",
                json.dumps({"text": text}, ensure_ascii=False).encode(),
                content_type=_JSON,
            )
        except StorageUnavailable:
            raise Deferred from None


class _Asker:
    """Binds a core's `ask` to LlmClient (quota guard, audit row). `attempt` is the core's own
    retry: 1, then 2."""

    def __init__(
        self,
        llm: LlmClient,
        *,
        task: Task,
        version: str,
        event: SubmissionCreatedEvent,
        pipeline_run_id: uuid.UUID,
        payload: dict[str, Any],
    ) -> None:
        self.llm, self.version = llm, version
        self.task: Task = task
        self.event, self.run_id, self.payload = event, pipeline_run_id, payload
        self.calls = 0

    def _call(self, prompt: ChunkPrompt | ReadPrompt) -> str:
        self.calls += 1
        images = (prompt.image,) if isinstance(prompt, ReadPrompt) else ()
        request = LlmRequest(
            task=self.task,
            user_id=self.event.user_id,
            subject_id=self.event.payload.subject_id,
            pipeline_run_id=self.run_id,
            prompt_version=self.version,
            attempt=min(self.calls, 2),
            system=prompt.system,
            user=prompt.user,
            output_schema=prompt.output_schema,
            payload=self.payload,
            images=images,
        )
        return self.llm.call(request, deadline=time.monotonic() + CALL_SECONDS).text

    def __call__(self, prompt: Any) -> str:
        return self._call(prompt)


class ProcessSubmission:
    """The handler of `submission.created.v1`. `llm` is None when the model is disabled."""

    def __init__(
        self,
        *,
        storage: ObjectStorage,
        redis: Redis,
        llm: LlmClient | None,
        sessions: SessionFactory,
        stream: str = OUT_STREAM,
    ) -> None:
        self.storage, self.redis, self.llm = storage, redis, llm
        self.sessions, self.stream = sessions, stream

    def __call__(self, session: Session, event: Event) -> None:
        if not isinstance(event, SubmissionCreatedEvent):
            raise TypeError("ProcessSubmission handles submission.created.v1 only")
        key = result_key_for(event)
        if not self._written(key):
            try:
                body = self._result(event)
            except _Fail as failure:
                _log.warning("submission failed", extra={"outcome": failure.code})
                self._send(event, "failed", failure.reason)
                return
            self._put(key, body)
        self._send(event, "processed", key)

    # --- the work -----------------------------------------------------------------------

    def _result(self, event: SubmissionCreatedEvent) -> bytes:
        if self.llm is None:
            raise _Fail("llm_unavailable", "disabled")
        context = self._context(event)
        work = _Work()
        try:
            pages = self._scope_pages(event, context, work)
            notes_parts = self._notes_parts(event, self.llm, work)
            if not pages and not notes_parts:
                raise _Fail("unreadable", "nothing_readable")
            batches = _batches(pages, notes_parts)
            drafts = self._draft(event, self.llm, context, batches, work)
        except _Fail:
            raise
        except (LlmUnavailableError, QuotaExceededError):
            raise _Fail("llm_unavailable", "llm_unavailable") from None
        except AuditUnavailableError:
            raise Deferred from None
        except Deferred:
            raise
        except (ChunkInputError, ChunkInvalidError):
            raise _Fail("internal_error", "model_output") from None
        except Exception:
            _log.exception("submission processing crashed")  # no text in exceptions (ADR-0013)
            raise _Fail("internal_error", "unexpected") from None
        try:
            return self._dump(event, drafts, work)
        except ValidationError:
            _log.error("result broke its own contract")
            raise _Fail("internal_error", "contract") from None

    def _context(self, event: SubmissionCreatedEvent) -> SubmissionContext:
        raw = self._get(event.payload.context_key, MAX_CONTEXT_BYTES)
        if raw is None:
            raise _Fail("unreadable", "context_missing")
        try:
            return parse_context(raw)
        except ValidationError:
            raise _Fail("internal_error", "context_invalid") from None

    def _get(self, key: str, max_bytes: int) -> bytes | None:
        if not key.startswith("users/"):  # the consumer checked the owner; never read elsewhere
            return None
        try:
            return self.storage.get(key, max_bytes=max_bytes)
        except (ObjectNotFound, ObjectTooLarge):
            return None
        except StorageUnavailable:
            raise Deferred from None

    # --- the scope: pages of the mentioned documents -------------------------------------

    def _scope_pages(
        self, event: SubmissionCreatedEvent, context: SubmissionContext, work: _Work
    ) -> list[_Page]:
        owner = f"users/{event.user_id}/"
        subject = f"{owner}subjects/{event.payload.subject_id}"
        by_doc: dict[uuid.UUID, dict[int, str] | None] = {}
        pages: dict[tuple[uuid.UUID, int], _Page] = {}
        truncated = False
        for mention in context.mentions:
            if mention.first_page is None or mention.last_page is None:
                work.skip("page", 0, "no_text")  # no positions: nothing to read, nothing guessed
                continue
            if mention.document_id not in by_doc:
                by_doc[mention.document_id] = self._page_texts(subject, owner, mention.document_id)
            texts = by_doc[mention.document_id]
            for number in range(mention.first_page, mention.last_page + 1):
                found = pages.get((mention.document_id, number))
                if found is not None:  # ranges overlap: the page counts once, in every section
                    if mention.section_id and mention.section_id not in found.section_ids:
                        found.section_ids.append(mention.section_id)
                    continue
                if len(pages) >= MAX_SCOPE_PAGES:
                    truncated = True
                    continue
                text = None if texts is None else texts.get(number)
                if not isinstance(text, str) or not text.strip():
                    work.skip("page", number, "no_text")
                    continue
                if len(text) > MAX_PAGE_CHARS:
                    text = text[:MAX_PAGE_CHARS]
                    work.skip("page", number, "truncated")
                pages[(mention.document_id, number)] = _Page(
                    mention.document_id,
                    number,
                    text.replace("\x00", ""),
                    [mention.section_id] if mention.section_id else [],
                )
        if truncated:
            work.skip("page", MAX_SCOPE_PAGES + 1, "truncated")
        return list(pages.values())

    def _page_texts(
        self, subject: str, owner: str, document_id: uuid.UUID
    ) -> dict[int, str] | None:
        pointer = self._get(f"{subject}/documents/{document_id}/index.json", MAX_POINTER_BYTES)
        if pointer is None:
            return None
        try:
            text_key = json.loads(pointer)["page_text_key"]
            if not isinstance(text_key, str) or not text_key.startswith(owner):
                return None
            raw = self._get(text_key, MAX_INDEX_BYTES)
            if raw is None:
                return None
            return {p["page"]: p["text"] for p in json.loads(raw)["pages"]}
        except (ValueError, KeyError, TypeError):
            return None

    # --- the learner's own files -----------------------------------------------------------

    def _notes_parts(self, event: SubmissionCreatedEvent, llm: LlmClient, work: _Work) -> list[str]:
        """Text of the submitted files in order. Images and scans are read last, by vision."""
        parts: list[str] = []
        images: list[ImageSource] = []
        file_of: dict[int, int] = {}  # image ordinal -> index of its file, for `skipped`
        total = 0
        for index, file in enumerate(event.payload.file_keys, 1):
            raw = self._get(file.object_key, MAX_FILE_BYTES)
            if raw is None:
                work.skip("note", index, "unreadable")
                continue
            if file.mime in IMAGE_MIMES:
                images.append(ImageSource(len(images) + 1, raw))
                file_of[len(images)] = index
                continue
            if file.mime == "application/pdf":
                text = self._pdf(raw, index, images, file_of, work)
            else:
                text = _office_or_text(file.mime, raw)
            if text is None:
                work.skip("note", index, "unreadable")
            elif not text.strip():
                work.skip("note", index, "no_text")
            else:
                if total + len(text) > MAX_NOTES_TOTAL_CHARS:
                    text = text[: max(0, MAX_NOTES_TOTAL_CHARS - total)]
                    work.skip("note", index, "truncated")
                total += len(text)
                if text.strip():
                    parts.append(text.replace("\x00", ""))
        if images:
            parts.extend(self._read_images(event, llm, images, file_of, work))
        return parts

    def _pdf(
        self,
        raw: bytes,
        index: int,
        images: list[ImageSource],
        file_of: dict[int, int],
        work: _Work,
    ) -> str | None:
        texts: list[str] = []
        chars = 0
        try:
            with open_pdf(raw) as pdf:
                for page_index in range(pdf.page_count):
                    # Enough scans collected (one more makes the cap visible) and enough text.
                    if len(images) > read_task.MAX_IMAGES or chars > MAX_NOTES_TOTAL_CHARS:
                        work.skip("note", index, "truncated")
                        break
                    page = pdf.extract_text(page_index)
                    if page.needs_vision:
                        rendered = pdf.render_page(page_index, max_px=RENDER_PX)
                        images.append(ImageSource(len(images) + 1, rendered.png))
                        file_of[len(images)] = index
                    elif page.text.strip():
                        texts.append(page.text)
                        chars += len(page.text)
        except PdfError:
            return None
        return "\n\n".join(texts)

    def _read_images(
        self,
        event: SubmissionCreatedEvent,
        llm: LlmClient,
        images: list[ImageSource],
        file_of: dict[int, int],
        work: _Work,
    ) -> list[str]:
        prompt = Prompt(
            version=read_task.PROMPT_VERSION,
            text=read_task.system_prompt(),
            sha256=hashlib.sha256(read_task.system_prompt().encode()).hexdigest(),
        )
        run_id = self._start_run(event, read_task.TASK, prompt)
        asker = _Asker(
            llm,
            task="read_notes",
            version=read_task.PROMPT_VERSION,
            event=event,
            pipeline_run_id=run_id,
            payload={"kind": "read_notes"},
        )
        try:
            result = read_images(images, asker, StorageVisionCache(self.storage, event.user_id))
        except BaseException as error:
            self._finish_run(run_id, _code(error))
            raise
        self._finish_run(run_id, None)
        for skip in result.skipped:
            work.skip("note", file_of.get(skip.ref, skip.ref), skip.reason)
        return [part.text for part in result.parts]

    # --- the drafts -----------------------------------------------------------------------

    def _draft(
        self,
        event: SubmissionCreatedEvent,
        llm: LlmClient,
        context: SubmissionContext,
        batches: list[_Batch],
        work: _Work,
    ) -> list[Draft]:
        prompt = draft_task.prompt()
        run_id = self._start_run(event, draft_task.TASK, prompt)
        merged: dict[str, Draft] = {}
        try:
            for batch in batches:
                for part in self._split_to_fit(event, llm, run_id, context, batch, work):
                    for draft in part:
                        kept = merged.get(draft.draft_key)
                        merged[draft.draft_key] = draft if kept is None else _union(kept, draft)
        except BaseException as error:
            self._finish_run(run_id, _code(error))
            raise
        self._finish_run(run_id, None)
        drafts = list(merged.values())
        if len(drafts) > MAX_DRAFTS:
            work.dropped_drafts += len(drafts) - MAX_DRAFTS
            drafts = drafts[:MAX_DRAFTS]
        return drafts

    def _split_to_fit(
        self,
        event: SubmissionCreatedEvent,
        llm: LlmClient,
        run_id: uuid.UUID,
        context: SubmissionContext,
        batch: _Batch,
        work: _Work,
    ) -> list[list[Draft]]:
        """The drafts of a batch; one the model cannot take is halved by pages until it fits."""
        try:
            return [self._draft_batch(event, llm, run_id, context, batch, work)]
        except ChunkInputError:
            if len(batch.pages) < 2:
                raise
            mid = len(batch.pages) // 2
            first = _Batch(batch.pages[:mid], batch.notes, batch.notes_offset)
            second = _Batch(batch.pages[mid:], None, 0)
            return [
                *self._split_to_fit(event, llm, run_id, context, first, work),
                *self._split_to_fit(event, llm, run_id, context, second, work),
            ]

    def _draft_batch(
        self,
        event: SubmissionCreatedEvent,
        llm: LlmClient,
        run_id: uuid.UUID,
        context: SubmissionContext,
        batch: _Batch,
        work: _Work,
    ) -> list[Draft]:
        request = _request(event, context, batch)
        cache_key = self._batch_key(event, request)
        cached = self._load_batch(cache_key)
        if cached is not None:
            drafts, dropped_anchors, dropped_drafts = cached
        else:
            asker = _Asker(
                llm,
                task="draft_units",
                version=draft_task.PROMPT_VERSION,
                event=event,
                pipeline_run_id=run_id,
                payload={"sources": _sources(request)},
            )
            outcome: DraftOutcome = draft_units(request, asker)
            if outcome.status == "pending_ai":
                raise QuotaExceededError(hard=False, window="day")
            drafts = [_shift_notes(d, batch.notes_offset) for d in outcome.drafts]
            dropped_anchors = sum(1 for d in outcome.dropped if d.kind == "anchor")
            dropped_drafts = sum(1 for d in outcome.dropped if d.kind == "unit")
            self._save_batch(cache_key, drafts, dropped_anchors, dropped_drafts)
        work.dropped_anchors += dropped_anchors
        work.dropped_drafts += dropped_drafts
        return drafts

    def _batch_key(self, event: SubmissionCreatedEvent, request: DraftRequest) -> str:
        digest = hashlib.sha256(request.model_dump_json().encode()).hexdigest()[:32]
        payload = event.payload
        return (
            f"users/{event.user_id}/derived/submission/{payload.submission_id}/"
            f"batch-{draft_task.PROMPT_VERSION}-{digest}.json"
        )

    def _load_batch(self, key: str) -> tuple[list[Draft], int, int] | None:
        try:
            raw = self.storage.get(key, max_bytes=MAX_CACHED_BYTES)
            data = json.loads(raw)
            return (
                _DRAFTS.validate_python(data["drafts"]),
                int(data["dropped_anchors"]),
                int(data["dropped_drafts"]),
            )
        except (ObjectNotFound, ObjectTooLarge, ValueError, KeyError, TypeError):
            return None
        except StorageUnavailable:
            raise Deferred from None

    def _save_batch(self, key: str, drafts: list[Draft], anchors: int, units: int) -> None:
        body = {
            "drafts": json.loads(_DRAFTS.dump_json(drafts)),
            "dropped_anchors": anchors,
            "dropped_drafts": units,
        }
        try:
            self.storage.put(key, json.dumps(body, ensure_ascii=False).encode(), content_type=_JSON)
        except StorageUnavailable:
            raise Deferred from None

    # --- the result file ----------------------------------------------------------------

    def _dump(self, event: SubmissionCreatedEvent, drafts: list[Draft], work: _Work) -> bytes:
        result = SessionResultV2(
            version=2,
            study_session_id=event.payload.study_session_id,
            drafts=[_wire(d) for d in drafts],
            dropped=WireDropped(anchors=work.dropped_anchors, drafts=work.dropped_drafts),
            skipped=work.skipped,
        )
        return result.model_dump_json().encode()

    def _written(self, key: str) -> bool:
        try:
            self.storage.get(key, max_bytes=MAX_RESULT_BYTES)
        except ObjectNotFound:
            return False
        except ObjectTooLarge:
            return True
        except StorageUnavailable:
            raise Deferred from None
        return True

    def _put(self, key: str, body: bytes) -> None:
        try:
            self.storage.put(key, body, content_type=_JSON)
        except StorageUnavailable:
            raise Deferred from None

    # --- audit rows and events ----------------------------------------------------------

    def _start_run(self, event: SubmissionCreatedEvent, task: Task, prompt: Any) -> uuid.UUID:
        """Committed before any call: no paid call without its run."""
        run = PipelineRun(
            user_id=event.user_id,
            subject_id=event.payload.subject_id,
            task=task,
            prompt_version=prompt.version,
            prompt_sha256=prompt.sha256,
        )
        try:
            with self.sessions() as session:
                session.add(run)
                session.commit()
        except Exception as error:
            _log.exception("pipeline_run not written")
            raise AuditUnavailableError from error
        return run.id

    def _finish_run(self, run_id: uuid.UUID, error_code: str | None) -> None:
        try:
            with self.sessions() as session:
                session.execute(
                    update(PipelineRun)
                    .where(PipelineRun.id == run_id)
                    .values(
                        status="failed" if error_code else "succeeded",
                        error_code=error_code,
                        finished_at=func.now(),
                    )
                )
                session.commit()
        except Exception:
            _log.exception("pipeline_run not closed")  # the work is done; the row stays running

    def _send(self, event: SubmissionCreatedEvent, kind: str, value: str) -> None:
        payload = event.payload
        base: dict[str, Any] = {
            # From the INCOMING event: the same event again gives the same id (the consumer of
            # the other side drops it); a new event for the same submission gives a new one.
            "event_id": uuid.uuid5(_NAMESPACE, f"{kind}:{event.event_id}"),
            "schema_version": 1,
            "occurred_at": datetime.now(UTC),
            "user_id": event.user_id,
            "trace_context": event.trace_context,
        }
        out: Event
        if kind == "processed":
            out = SubmissionProcessedEvent(
                **base,
                event_type="submission.processed.v1",
                payload=SubmissionProcessed(
                    submission_id=payload.submission_id,
                    study_session_id=payload.study_session_id,
                    run_id=run_id_for(event.event_id),
                    result_key=value,
                ),
            )
        else:
            out = SubmissionFailedEvent(
                **base,
                event_type="submission.failed.v1",
                payload=SubmissionFailed(
                    submission_id=payload.submission_id,
                    study_session_id=payload.study_session_id,
                    run_id=run_id_for(event.event_id),
                    reason=value,  # type: ignore[arg-type]
                ),
            )
        self.redis.xadd(
            self.stream, {"envelope": dump_event(out)}, maxlen=STREAM_MAXLEN, approximate=True
        )


# --- pure helpers --------------------------------------------------------------------------


def _office_or_text(mime: str, raw: bytes) -> str | None:
    try:
        if mime in TEXT_MIMES:
            return raw.decode("utf-8", errors="replace")
        if mime == DOCX:
            return "\n".join(p.text for p in read_docx(raw).paragraphs)
        if mime == PPTX:
            return "\n\n".join(s.text for s in read_pptx(raw).slides if s.text.strip())
    except Exception:  # the readers' errors name the file; "unreadable" is enough
        return None
    return None


def _chunk_notes(parts: list[str]) -> list[tuple[int, str]]:
    """The learner's text as pieces of at most `MAX_NOTES_CHARS`, each with its offset in the
    whole text (parts joined by a blank line), cut at part boundaries when it can be and hard
    when one part is longer than a piece."""
    chunks: list[tuple[int, str]] = []
    whole = ""
    start = 0
    for part in parts:
        piece = part if not whole else "\n\n" + part
        if whole and len(whole) + len(piece) <= MAX_NOTES_CHARS:
            whole += piece
            continue
        if whole:
            chunks.append((start, whole))
            start += len(whole) + 2
        whole = ""
        text = part
        while len(text) > MAX_NOTES_CHARS:
            chunks.append((start, text[:MAX_NOTES_CHARS]))
            start += MAX_NOTES_CHARS
            text = text[MAX_NOTES_CHARS:]
        whole = text
    if whole:
        chunks.append((start, whole))
    return chunks


def _batches(pages: list[_Page], notes_parts: list[str]) -> list[_Batch]:
    page_batches: list[list[_Page]] = []
    size = 0
    for page in pages:
        if (
            not page_batches
            or len(page_batches[-1]) >= BATCH_PAGES
            or size + len(page.text) > BATCH_CHARS
        ):
            page_batches.append([])
            size = 0
        page_batches[-1].append(page)
        size += len(page.text)
    chunks = _chunk_notes(notes_parts)
    out: list[_Batch] = []
    for n in range(max(len(page_batches), len(chunks))):
        pages_n = page_batches[n] if n < len(page_batches) else []
        offset, text = chunks[n] if n < len(chunks) else (0, None)
        out.append(_Batch(pages_n, text, offset))
    return out


def _request(
    event: SubmissionCreatedEvent, context: SubmissionContext, batch: _Batch
) -> DraftRequest:
    order: dict[uuid.UUID, list[ScopedPage]] = {}
    for p in batch.pages:
        order.setdefault(p.document_id, []).append(
            ScopedPage(page_no=p.number, text=p.text, section_ids=p.section_ids)
        )
    return DraftRequest(
        session_id=event.payload.study_session_id,
        scope=[
            ScopedDoc(document_id=doc, name=f"document {n}", pages=pages)
            for n, (doc, pages) in enumerate(order.items(), 1)
        ],
        submission_text=batch.notes,
        description=context.description,
    )


def _sources(request: DraftRequest) -> list[dict[str, str]]:
    """Label and text of what the model may anchor to; for the fake provider only."""
    chunk = to_chunk_request(request)
    out = [
        {"label": f"D{d}.p{p.page_no}", "text": p.text}
        for d, doc in enumerate(chunk.documents, 1)
        for p in doc.pages
    ]
    if chunk.notes_text is not None:
        out.append({"label": "notes", "text": chunk.notes_text})
    return out


def _shift_notes(draft: Draft, offset: int) -> Draft:
    """Offsets of notes anchors are in the whole submitted text, not in the piece asked."""
    if not offset:
        return draft
    return dataclasses.replace(
        draft,
        anchors=[
            dataclasses.replace(a, start=a.start + offset, end=a.end + offset)
            if a.document_id is None
            else a
            for a in draft.anchors
        ],
    )


def _anchor_id(a: DraftAnchor) -> tuple[object, ...]:
    return (a.document_id, a.page, a.start, a.end)


def _union(kept: Draft, other: Draft) -> Draft:
    """Two drafts with one key (the same first quote): one draft, every anchor and section."""
    known = {_anchor_id(a) for a in kept.anchors}
    anchors = kept.anchors + [a for a in other.anchors if _anchor_id(a) not in known]
    anchors.sort(key=draft_task.anchor_order)
    sections = kept.section_ids + [s for s in other.section_ids if s not in kept.section_ids]
    return dataclasses.replace(kept, anchors=anchors, section_ids=sections)


def _wire(draft: Draft) -> WireDraft:
    """The contract carries one section per draft; a draft over two sections keeps the first
    (the others stay with the draft until core asks for a list: T7.7 plan, question 2)."""
    return WireDraft(
        draft_key=draft.draft_key,
        quote_hash=draft.quote_hash,
        title=draft.title[:200],
        content=draft.content,
        kind=draft.kind,
        section_id=draft.section_ids[0] if draft.section_ids else None,
        suggested_section_id=None,
        anchors=[
            WireAnchor(
                source=a.source,
                document_id=a.document_id,
                page_no=a.page,
                start=a.start,
                end=a.end,
                quote_text=a.quote,
            )
            for a in draft.anchors
        ],
    )


def _code(error: BaseException) -> str:
    if isinstance(error, LlmUnavailableError | QuotaExceededError):
        return "llm_unavailable"
    if isinstance(error, ChunkInvalidError):
        return "output_invalid"
    return "internal_error"


# --- The fake provider (AI_LLM_PROVIDER=fake: local and test only) --------------------------


def fake_read_notes(request: LlmRequest) -> str:
    """A reading that depends only on the image: same image, same words."""
    digest = request.images[0].sha256[:8] if request.images else "none"
    return json.dumps(
        {"text": f"Ghi chú trong ảnh {digest}: ty the la noi hop ho hap.", "legible": True}
    )


__all__ = [
    "ProcessSubmission",
    "fake_read_notes",
    "result_key_for",
    "run_id_for",
]
