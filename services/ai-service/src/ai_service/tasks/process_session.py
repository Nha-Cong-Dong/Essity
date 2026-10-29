"""Process a confirmed study session (T4.16b, US-02/02b/04b): `session.confirmed.v1` in, a result
file and `session.processed.v1` out (`session.progress.v1` on the way, `session.failed.v1` when
it cannot be done).

Reads the page text of the ranges (through the per-document pointer the indexer writes, T4.7) and
the learner's text notes, splits them into knowledge units (T4.15, batched), writes level-1
questions for the new units (T4.16a, batched), and stores everything in one claim-check file
(`contracts/files/session-result.v1`): units with anchors, anchors to add to existing units,
questions. core-api persists it (T4.17). Image and PDF notes are skipped with a recorded reason
until T4.14; that never fails the session.

Idempotent on the event (consumer.Handler): the result key and the ids of the events sent derive
from the incoming event's id, and a result already written is only announced again. Nothing here
logs page text, notes or model output (ADR-0013): rule names and counts only.

Deferred, not failed: the storage or the audit trail not answering. Failed (an event, not an
exception): the model unavailable or over quota (`llm_unavailable`), nothing readable
(`unreadable`), a bad range or a model that breaks the output rules on every attempt
(`internal_error`).
"""

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

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
from ai_service.llm.client import AuditUnavailableError, LlmClient, LlmUnavailableError
from ai_service.llm.quota import QuotaExceededError
from ai_service.llm.types import LlmRequest, Task
from ai_service.messaging.consumer import Deferred
from ai_service.messaging.dead_letter import STREAM_MAXLEN
from ai_service.messaging.envelope import (
    Event,
    SessionConfirmedEvent,
    SessionFailed,
    SessionFailedEvent,
    SessionProcessed,
    SessionProcessedEvent,
    SessionProgress,
    SessionProgressEvent,
    dump_event,
)
from ai_service.tasks import chunk_units as chunk_task
from ai_service.tasks import generate_questions as question_task
from ai_service.tasks.chunk_models import (
    MAX_UNITS_OUT,
    Anchor,
    ChunkRequest,
    DocInput,
    ExistingUnit,
    NewUnit,
    PageInput,
)
from ai_service.tasks.chunk_units import ChunkInputError, ChunkInvalidError, ChunkPrompt
from ai_service.tasks.generate_questions import (
    QuestionInputError,
    QuestionPrompt,
    QuestionsInvalidError,
)
from ai_service.tasks.question_models import (
    MAX_QUOTE_CHARS,
    MAX_QUOTES_PER_UNIT,
    MAX_SUMMARY_CHARS,
    MAX_TITLE_CHARS,
    GeneratedQuestion,
    QuestionRequest,
    QuestionUnit,
)

OUT_STREAM = "events.ai"
_NAMESPACE = uuid.UUID("0d3c6b52-4e0a-4d0b-8a8e-3f1d7c1c9a55")
_JSON = "application/json"

MAX_INDEX_BYTES = 20_000_000
MAX_NOTE_BYTES = 200_000
MAX_RESULT_BYTES = 8_000_000
BATCH_PAGES = 20
BATCH_CHARS = 100_000
QUESTION_BATCH = 20
CALL_SECONDS = 90.0
CACHE_PREFIX = "ai:session:"
CACHE_SECONDS = 86_400
TEXT_NOTES = frozenset({"text/plain", "text/markdown"})

_log = logging.getLogger(__name__)


def run_id_for(event_id: uuid.UUID) -> uuid.UUID:
    return uuid.uuid5(_NAMESPACE, f"run:{event_id}")


def unit_id_for(event_id: uuid.UUID, n: int) -> uuid.UUID:
    return uuid.uuid5(_NAMESPACE, f"unit:{event_id}:{n}")


def result_key_for(event: SessionConfirmedEvent) -> str:
    """`users/<user>/subjects/<subject>/sessions/<session>/result-<event>.json`."""
    prefix = subject_prefix(event)
    return f"{prefix}/sessions/{event.payload.study_session_id}/result-{event.event_id}.json"


def subject_prefix(event: SessionConfirmedEvent) -> str:
    return f"users/{event.user_id}/subjects/{event.payload.subject_id}"


class _Fail(Exception):
    def __init__(self, reason: str, code: str) -> None:
        super().__init__(code)
        self.reason, self.code = reason, code


@dataclass
class _Unit:
    unit_id: uuid.UUID
    new: NewUnit


@dataclass
class _Work:
    """What one run collects. `skipped` holds rule names and numbers, never text."""

    units: list[_Unit] = field(default_factory=lambda: list[_Unit]())
    merges: dict[uuid.UUID, list[Anchor]] = field(
        default_factory=lambda: dict[uuid.UUID, list[Anchor]]()
    )
    questions: list[GeneratedQuestion] = field(default_factory=lambda: list[GeneratedQuestion]())
    skipped: list[dict[str, Any]] = field(default_factory=lambda: list[dict[str, Any]]())
    dropped_anchors: int = 0
    dropped_units: int = 0
    dropped_questions: int = 0


def _anchor_key(a: Anchor) -> tuple[object, ...]:
    return (a.source, a.document_id, a.page_no, a.start, a.end)


def _add_anchors(into: list[Anchor], more: list[Anchor]) -> list[Anchor]:
    seen = {_anchor_key(a) for a in into}
    return into + [a for a in more if _anchor_key(a) not in seen]


class _Asker:
    """Binds the cores' `ask` to LlmClient (quota guard, audit row). `attempt` is the core's
    own retry: 1, then 2."""

    def __init__(
        self,
        llm: LlmClient,
        *,
        task: Task,
        version: str,
        event: SessionConfirmedEvent,
        pipeline_run_id: uuid.UUID,
        payload: dict[str, Any],
    ) -> None:
        self.llm, self.version = llm, version
        self.task: Task = task
        self.event, self.run_id, self.payload = event, pipeline_run_id, payload
        self.calls = 0

    def __call__(self, prompt: ChunkPrompt | QuestionPrompt) -> str:
        self.calls += 1
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
        )
        return self.llm.call(request, deadline=time.monotonic() + CALL_SECONDS).text


class ProcessSession:
    """The handler of `session.confirmed.v1`. `llm` is None when the model is disabled."""

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
        if not isinstance(event, SessionConfirmedEvent):
            raise TypeError("ProcessSession handles session.confirmed.v1 only")
        key = result_key_for(event)
        if not self._written(key):
            body = self._recall(f"result:{event.event_id}")
            if body is None:
                try:
                    body = self._result(event)
                except _Fail as failure:
                    _log.warning("session failed", extra={"outcome": failure.code})
                    self._send(event, "failed", failure.reason, None)
                    return
                self._remember(f"result:{event.event_id}", body)
            self._put(key, body)
        self._send(event, "processed", key, None)
        self._forget(event)

    # --- the work -----------------------------------------------------------------------

    def _result(self, event: SessionConfirmedEvent) -> bytes:
        payload = event.payload
        if any(r.first > r.last for r in payload.ranges):
            raise _Fail("internal_error", "range_inverted")
        if self.llm is None:
            raise _Fail("llm_unavailable", "disabled")
        work = self._load_work(event)
        pages: list[tuple[uuid.UUID, int, str]] = []
        notes: str | None = None
        if work is None:
            work = _Work()
            pages = self._read_pages(event, work)
            notes = self._read_notes(event, work)
            if not pages and not notes:
                raise _Fail("unreadable", "nothing_readable")
            self._progress(event, "reading_notes", 10)
            split = True
        else:
            split = False
        try:
            if split:
                self._split(event, self.llm, pages, notes, work)
                self._save_work(event, work)
            self._progress(event, "anchoring", 70)
            self._ask_questions(event, self.llm, work)
        except (LlmUnavailableError, QuotaExceededError):
            raise _Fail("llm_unavailable", "llm_unavailable") from None
        except AuditUnavailableError:
            raise Deferred from None
        except (ChunkInputError, ChunkInvalidError, QuestionInputError, QuestionsInvalidError):
            raise _Fail("internal_error", "model_output") from None
        except Deferred:
            raise
        except Exception:
            _log.exception("session processing crashed")  # no text in exceptions (ADR-0013)
            raise _Fail("internal_error", "unexpected") from None
        return self._dump(event, work)

    # --- paid results kept across a redelivery (Deferred): Redis, best effort, one day ---------

    def _recall(self, name: str) -> bytes | None:
        try:
            value = self.redis.get(f"{CACHE_PREFIX}{name}")
        except Exception:
            return None
        if isinstance(value, str):
            return value.encode()
        return value if isinstance(value, bytes) else None

    def _remember(self, name: str, body: bytes) -> None:
        try:
            self.redis.set(f"{CACHE_PREFIX}{name}", body, ex=CACHE_SECONDS)
        except Exception:
            _log.warning("paid result not cached")

    def _forget(self, event: SessionConfirmedEvent) -> None:
        """The result is stored: session text must not linger in Redis (ADR-0001/0007)."""
        try:
            self.redis.delete(
                f"{CACHE_PREFIX}result:{event.event_id}", f"{CACHE_PREFIX}chunk:{event.event_id}"
            )
        except Exception:
            _log.warning("paid result cache not deleted")

    def _save_work(self, event: SessionConfirmedEvent, work: _Work) -> None:
        data: dict[str, Any] = {
            "units": [
                {"unit_id": str(u.unit_id), "new": json.loads(u.new.model_dump_json())}
                for u in work.units
            ],
            "merges": {
                str(k): [json.loads(a.model_dump_json()) for a in v] for k, v in work.merges.items()
            },
            "skipped": work.skipped,
            "dropped_anchors": work.dropped_anchors,
            "dropped_units": work.dropped_units,
        }
        self._remember(f"chunk:{event.event_id}", json.dumps(data).encode())

    def _load_work(self, event: SessionConfirmedEvent) -> _Work | None:
        raw = self._recall(f"chunk:{event.event_id}")
        if raw is None:
            return None
        try:
            data = json.loads(raw)
            work = _Work(
                skipped=data["skipped"],
                dropped_anchors=data["dropped_anchors"],
                dropped_units=data["dropped_units"],
            )
            work.units = [
                _Unit(uuid.UUID(u["unit_id"]), NewUnit.model_validate(u["new"]))
                for u in data["units"]
            ]
            work.merges = {
                uuid.UUID(k): [Anchor.model_validate(a) for a in v]
                for k, v in data["merges"].items()
            }
        except (ValueError, KeyError, TypeError):
            return None
        return work

    def _get(self, key: str, max_bytes: int) -> bytes | None:
        try:
            return self.storage.get(key, max_bytes=max_bytes)
        except (ObjectNotFound, ObjectTooLarge):
            return None
        except StorageUnavailable:
            raise Deferred from None

    def _read_pages(
        self, event: SessionConfirmedEvent, work: _Work
    ) -> list[tuple[uuid.UUID, int, str]]:
        owner = f"users/{event.user_id}/"
        out: list[tuple[uuid.UUID, int, str]] = []
        seen: set[tuple[uuid.UUID, int]] = set()  # ranges may overlap; a page counts once
        for r in event.payload.ranges:
            pointer = self._get(
                f"{subject_prefix(event)}/documents/{r.document_id}/index.json", MAX_NOTE_BYTES
            )
            pages_by_no = None
            if pointer is not None:
                try:
                    text_key = json.loads(pointer)["page_text_key"]
                    ok = isinstance(text_key, str) and text_key.startswith(owner)
                    raw = self._get(text_key, MAX_INDEX_BYTES) if ok else None
                    if raw is not None:
                        pages_by_no = {p["page"]: p["text"] for p in json.loads(raw)["pages"]}
                except (ValueError, KeyError, TypeError):
                    pages_by_no = None
            for number in range(r.first, r.last + 1):
                if (r.document_id, number) in seen:
                    continue
                seen.add((r.document_id, number))
                text = None if pages_by_no is None else pages_by_no.get(number)
                if not isinstance(text, str) or not text.strip():
                    work.skipped.append({"kind": "page", "ref": number, "reason": "no_text"})
                    continue
                if len(text) > chunk_task.MAX_PAGE_CHARS:
                    text = text[: chunk_task.MAX_PAGE_CHARS]
                    work.skipped.append({"kind": "page", "ref": number, "reason": "truncated"})
                out.append((r.document_id, number, text.replace("\x00", "")))
        return out

    def _read_notes(self, event: SessionConfirmedEvent, work: _Work) -> str | None:
        parts: list[str] = []
        for index, note in enumerate(event.payload.notes, 1):
            if note.mime not in TEXT_NOTES:
                work.skipped.append({"kind": "note", "ref": index, "reason": "needs_ocr"})
                continue
            raw = self._get(note.object_key, MAX_NOTE_BYTES)
            if raw is None:
                work.skipped.append({"kind": "note", "ref": index, "reason": "unreadable"})
                continue
            parts.append(raw.decode("utf-8", errors="replace").replace("\x00", ""))
        text = "\n\n".join(p for p in parts if p.strip())
        if len(text) > chunk_task.MAX_NOTES_CHARS:
            text = text[: chunk_task.MAX_NOTES_CHARS]
            work.skipped.append({"kind": "note", "ref": 0, "reason": "truncated"})
        return text or None

    def _batches(
        self, pages: list[tuple[uuid.UUID, int, str]]
    ) -> list[list[tuple[uuid.UUID, int, str]]]:
        batches: list[list[tuple[uuid.UUID, int, str]]] = []
        size = 0
        for page in pages:
            if not batches or len(batches[-1]) >= BATCH_PAGES or size + len(page[2]) > BATCH_CHARS:
                batches.append([])
                size = 0
            batches[-1].append(page)
            size += len(page[2])
        return batches

    def _split(
        self,
        event: SessionConfirmedEvent,
        llm: LlmClient,
        pages: list[tuple[uuid.UUID, int, str]],
        notes: str | None,
        work: _Work,
    ) -> None:
        batches = self._batches(pages) or [[]]
        run_id = self._start_run(event, chunk_task.TASK, chunk_task.load_prompt())
        known = [ExistingUnit(**e.model_dump()) for e in event.payload.existing_units]
        try:
            for n, batch in enumerate(batches):
                request = ChunkRequest(
                    documents=_documents(batch),
                    notes_text=notes if n == 0 else None,
                    existing_units=known[-chunk_task.MAX_EXISTING :],
                )
                asker = _Asker(
                    llm,
                    task="chunk_units",
                    version=chunk_task.PROMPT_VERSION,
                    event=event,
                    pipeline_run_id=run_id,
                    payload={"sources": _sources(request)},
                )
                result = chunk_task.chunk_units(request, asker)
                work.dropped_anchors += result.dropped_anchors
                work.dropped_units += result.dropped_units
                by_id = {u.unit_id: u for u in work.units}
                for merge in result.merges:
                    mine = by_id.get(merge.existing_unit_id)
                    if mine is not None:  # a unit made by an earlier batch of this run
                        mine.new = mine.new.model_copy(
                            update={"anchors": _add_anchors(mine.new.anchors, merge.anchors)}
                        )
                    else:
                        have = work.merges.get(merge.existing_unit_id, [])
                        work.merges[merge.existing_unit_id] = _add_anchors(have, merge.anchors)
                for unit in result.new_units:
                    if not unit.title.strip():  # one bad unit is dropped, not the session
                        work.dropped_units += 1
                        continue
                    made = _Unit(unit_id_for(event.event_id, len(work.units) + 1), unit)
                    work.units.append(made)
                    known.append(
                        ExistingUnit(
                            unit_id=made.unit_id,
                            title=unit.title[:200] or "-",
                            summary=unit.summary,
                        )
                    )
                self._progress(event, "splitting_units", 10 + 60 * (n + 1) // len(batches))
        except BaseException as error:
            self._finish_run(run_id, _code(error))
            raise
        self._finish_run(run_id, None)

    def _ask_questions(self, event: SessionConfirmedEvent, llm: LlmClient, work: _Work) -> None:
        if not work.units:
            return
        run_id = self._start_run(event, question_task.TASK, question_task.load_prompt())
        try:
            groups = [
                work.units[i : i + QUESTION_BATCH]
                for i in range(0, len(work.units), QUESTION_BATCH)
            ]
            for n, group in enumerate(groups):
                request = QuestionRequest(units=[_question_unit(u) for u in group])
                asker = _Asker(
                    llm,
                    task="generate_questions",
                    version=question_task.PROMPT_VERSION,
                    event=event,
                    pipeline_run_id=run_id,
                    payload={"labels": [f"U{i}" for i in range(1, len(group) + 1)]},
                )
                result = question_task.generate_questions(request, asker)
                work.questions.extend(result.questions)
                work.dropped_questions += len(result.dropped)
                self._progress(event, "writing_questions", 70 + 25 * (n + 1) // len(groups))
        except BaseException as error:
            self._finish_run(run_id, _code(error))
            raise
        self._finish_run(run_id, None)

    # --- the result file ----------------------------------------------------------------

    def _dump(self, event: SessionConfirmedEvent, work: _Work) -> bytes:
        body = {
            "version": 1,
            "study_session_id": str(event.payload.study_session_id),
            "units": [
                {"unit_id": str(u.unit_id)} | json.loads(u.new.model_dump_json())
                for u in work.units
            ],
            "merges": [
                {
                    "existing_unit_id": str(unit_id),
                    "anchors": [json.loads(a.model_dump_json()) for a in anchors],
                }
                for unit_id, anchors in work.merges.items()
            ],
            "questions": [_question_body(q) for q in work.questions],
            "dropped": {
                "anchors": work.dropped_anchors,
                "units": work.dropped_units,
                "questions": work.dropped_questions,
            },
            "skipped": work.skipped,
        }
        return json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode()

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

    def _start_run(self, event: SessionConfirmedEvent, task: str, prompt: Any) -> uuid.UUID:
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

    def _progress(self, event: SessionConfirmedEvent, step: str, percent: int) -> None:
        try:
            self._send(event, "progress", step, percent)
        except Exception:  # progress is best effort: it must not cost a paid run
            _log.warning("progress not sent")

    def _send(
        self, event: SessionConfirmedEvent, kind: str, value: str, percent: int | None
    ) -> None:
        payload = event.payload
        run_id = run_id_for(event.event_id)
        base: dict[str, Any] = {
            "event_id": uuid.uuid5(_NAMESPACE, f"{kind}:{event.event_id}:{value}:{percent}"),
            "schema_version": 1,
            "occurred_at": datetime.now(UTC),
            "user_id": event.user_id,
            "trace_context": event.trace_context,
        }
        out: Event
        if kind == "progress":
            out = SessionProgressEvent(
                **base,
                event_type="session.progress.v1",
                payload=SessionProgress(
                    study_session_id=payload.study_session_id,
                    run_id=run_id,
                    step=value,  # type: ignore[arg-type]
                    percent=percent or 0,
                ),
            )
        elif kind == "processed":
            out = SessionProcessedEvent(
                **base,
                event_type="session.processed.v1",
                payload=SessionProcessed(
                    study_session_id=payload.study_session_id, run_id=run_id, result_key=value
                ),
            )
        else:
            out = SessionFailedEvent(
                **base,
                event_type="session.failed.v1",
                payload=SessionFailed(
                    study_session_id=payload.study_session_id,
                    run_id=run_id,
                    reason=value,  # type: ignore[arg-type]
                ),
            )
        self.redis.xadd(
            self.stream, {"envelope": dump_event(out)}, maxlen=STREAM_MAXLEN, approximate=True
        )


def _question_body(question: GeneratedQuestion) -> dict[str, Any]:
    """Contract shape: the units a question covers are a list (level 1 has one, level 3 two or
    more; that rule lives in the code that makes the question, not in the schema)."""
    body = json.loads(question.model_dump_json())
    body["unit_ids"] = [body.pop("unit_id")]
    return body


def _code(error: BaseException) -> str:
    if isinstance(error, LlmUnavailableError | QuotaExceededError):
        return "llm_unavailable"
    if isinstance(error, ChunkInvalidError | QuestionsInvalidError):
        return "output_invalid"
    return "internal_error"


def _documents(batch: list[tuple[uuid.UUID, int, str]]) -> list[DocInput]:
    order: dict[uuid.UUID, list[PageInput]] = {}
    for document_id, number, text in batch:
        order.setdefault(document_id, []).append(PageInput(page_no=number, text=text))
    return [
        DocInput(document_id=doc, name=f"document {n}", pages=pages)
        for n, (doc, pages) in enumerate(order.items(), 1)
    ]


def _sources(request: ChunkRequest) -> list[dict[str, str]]:
    """Label and text of what the model may anchor to; for the fake provider only."""
    out = [
        {"label": f"D{d}.p{p.page_no}", "text": p.text}
        for d, doc in enumerate(request.documents, 1)
        for p in doc.pages
    ]
    if request.notes_text is not None:
        out.append({"label": "notes", "text": request.notes_text})
    return out


def _question_unit(unit: _Unit) -> QuestionUnit:
    quotes = [a.quote_text[:MAX_QUOTE_CHARS] for a in unit.new.anchors if a.quote_text.strip()]
    return QuestionUnit(
        unit_id=unit.unit_id,
        title=unit.new.title[:MAX_TITLE_CHARS],
        summary=unit.new.summary[:MAX_SUMMARY_CHARS],
        quotes=quotes[:MAX_QUOTES_PER_UNIT],
    )


# --- The fake provider (AI_LLM_PROVIDER=fake: local and test only) --------------------------


def fake_chunk(request: LlmRequest) -> str:
    """One unit per source, anchored to its first words."""
    units: list[dict[str, Any]] = []
    for source in request.payload["sources"][:MAX_UNITS_OUT]:
        quote = source["text"].strip()[:60].strip()
        if not quote:
            continue
        units.append(
            {
                "title": f"Ý chính {source['label']}",
                "summary": quote,
                "kind": "concept",
                "merge_into": None,
                "lineage": [],
                "anchors": [{"page": source["label"], "quote": quote}],
            }
        )
    return json.dumps({"units": units}, ensure_ascii=False)


def fake_questions(request: LlmRequest) -> str:
    """One question per unit."""
    return json.dumps(
        {
            "questions": [
                {
                    "unit": label,
                    "prompt": f"Nêu ý chính của {label}.",
                    "reference_answer": f"Ý chính của {label}.",
                    "rubric": "Nêu đúng ý chính; điểm một phần nếu thiếu.",
                }
                for label in request.payload["labels"]
            ]
        },
        ensure_ascii=False,
    )
