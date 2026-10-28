"""Turning a learner's sentence into a proposed session record (T4.10, US-02).

How a request becomes a prompt (same rules as grade, ADR-0010):

- The instructions are `prompts/extract_session/v<N>.md`, the system prompt. Only the nonce is
  filled in.
- The description, document names, table-of-contents lines and printed page labels are untrusted
  text. They go into the user message through `wrap_untrusted` (escaped, in a block tagged with a
  nonce drawn for the request). The model sees labels (`D1`, `D1.S3`), never ids.

Page numbers: the model points at a part the way the learner did (a section label, or page
numbers with a basis, printed or file). CODE turns that into FILE pages (`resolve_pages`); the
model never does arithmetic on pages or dates. `session_range` stores file pages; the card shows
the printed label too (PRD 7.1b, US-02 section 9 question 7).
"""

import datetime
import hashlib
import json
import logging
import re
import time
import unicodedata
import uuid
from contextlib import suppress
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, ValidationError
from sqlalchemy import func, update

from ai_service.db.models import PipelineRun
from ai_service.db.session import SessionFactory
from ai_service.llm.client import AuditUnavailableError, LlmClient, LlmUnavailableError
from ai_service.llm.quota import QuotaExceededError
from ai_service.llm.types import LlmRequest
from ai_service.tasks.extract_models import (
    MAX_QUESTION_CHARS,
    MAX_RANGES,
    MAX_SECTIONS_PER_RANGE,
    Clarify,
    ClarifyReason,
    Depth,
    ExtractDocument,
    ExtractRange,
    ExtractRequest,
    ExtractResponse,
    NoteOnly,
    Proposed,
)
from ai_service.tasks.grade import Prompt, new_nonce, wrap_untrusted

_log = logging.getLogger(__name__)

TASK = "extract_session"
PROMPT_VERSION = "v1"
_PROMPTS = Path(__file__).resolve().parents[3] / "prompts"
_NONCE_PLACEHOLDER = "{{NONCE}}"

# The whole request, retry included: core cuts at 5 s (T4.12). A second call only when this
# much is left.
DEADLINE_SECONDS = 4.0
RETRY_MIN_SECONDS = 1.0

# Normalization of the table of contents (what the prompt sees).
MAX_TOC_LEVEL = 2
MAX_SECTION_TITLE_CHARS = 120
MAX_SECTIONS_PER_DOCUMENT = 300
MAX_SECTIONS_TOTAL = 800
MAX_LABEL_SHOWN_CHARS = 32
MAX_STUDIED_DAYS_AGO = 366

OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["proposed", "note_only", "clarify"]},
        "studied_day": {
            "type": "object",
            "properties": {
                "days_ago": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
                "date": {"anyOf": [{"type": "string"}, {"type": "null"}]},
            },
            "required": ["days_ago", "date"],
            "additionalProperties": False,
        },
        "ranges": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "doc": {"type": "string"},
                    "kind": {"type": "string", "enum": ["section", "pages", "continue"]},
                    "from_section": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                    "to_section": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                    "basis": {
                        "anyOf": [{"type": "string", "enum": ["printed", "file"]}, {"type": "null"}]
                    },
                    "from_page": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
                    "to_page": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
                    "depth": {"type": "string", "enum": ["deep", "skim", "unclear"]},
                },
                "required": [
                    "doc",
                    "kind",
                    "from_section",
                    "to_section",
                    "basis",
                    "from_page",
                    "to_page",
                    "depth",
                ],
                "additionalProperties": False,
            },
        },
        "question": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        "reason": {
            "anyOf": [
                {
                    "type": "string",
                    "enum": [
                        "ambiguous_document",
                        "ambiguous_range",
                        "unknown_document",
                        "missing_info",
                    ],
                },
                {"type": "null"},
            ]
        },
        "candidates": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["status", "studied_day", "ranges", "question", "reason", "candidates"],
    "additionalProperties": False,
}


@lru_cache
def load_prompt(version: str = PROMPT_VERSION) -> Prompt:
    path = _PROMPTS / TASK / f"{version}.md"
    text = path.read_text("utf-8")
    return Prompt(
        version=version,
        text=text,
        sha256=hashlib.sha256(text.encode()).hexdigest(),
        path=str(path),
    )


# --- The documents as the model sees them ---------------------------------------------------


@dataclass(frozen=True)
class Section:
    label: str  # S1, S2, ... in the normalized order
    title: str
    level: int
    page: int  # file page, 1-based
    # Last page of the section, worked out on the whole toc as T4.7 wrote it (entries the
    # prompt does not show, with no title or cut for length, still end a section).
    end: int


@dataclass(frozen=True)
class Doc:
    label: str  # D1, D2, ...
    source: ExtractDocument
    sections: list[Section]


_CONTROL = re.compile(r"[\x00-\x1f\x7f  |]+")


def _clean(text: str, limit: int) -> str:
    """One line, no `|` (the toc line's separator), cut to `limit`."""
    return re.sub(r"\s+", " ", _CONTROL.sub(" ", text)).strip()[:limit].strip()


def _raw_section_end(document: ExtractDocument, index: int) -> int:
    """Before the next entry of the same level or above that has a page, in the toc as sent."""
    entry = document.toc[index]
    assert entry.page is not None
    for other in document.toc[index + 1 :]:
        if other.page is not None and other.level <= entry.level:
            return max(entry.page, other.page - 1)
    return document.page_count


def normalize_documents(request: ExtractRequest) -> list[Doc]:
    """The table of contents for the prompt, from what T4.7 wrote: entries with no title or no
    page are dropped, only the top levels stay, titles are cut, and a document keeps at most
    300 sections (800 in all), shallowest first, in their original order."""
    candidates: list[
        list[tuple[int, str, int, int]]
    ] = []  # per document: (index, title, level, page)
    for document in request.documents:
        entries: list[tuple[int, str, int, int]] = []
        for index, entry in enumerate(document.toc):
            title = _clean(entry.title, MAX_SECTION_TITLE_CHARS)
            if entry.page is None or not title or entry.level > MAX_TOC_LEVEL:
                continue
            entries.append((index, title, entry.level, entry.page))
        candidates.append(entries)

    per_document = min(MAX_SECTIONS_PER_DOCUMENT, MAX_SECTIONS_TOTAL // len(candidates))
    docs: list[Doc] = []
    for d, (document, entries) in enumerate(zip(request.documents, candidates, strict=True), 1):
        if len(entries) > per_document:
            keep = sorted(sorted(entries, key=lambda e: (e[2], e[0]))[:per_document])
        else:
            keep = entries
        sections = [
            Section(
                label=f"S{s}",
                title=title,
                level=level,
                page=page,
                end=_raw_section_end(document, index),
            )
            for s, (index, title, level, page) in enumerate(keep, 1)
        ]
        docs.append(Doc(label=f"D{d}", source=document, sections=sections))
    return docs


def _shown_label(document: ExtractDocument, page: int) -> str | None:
    """The printed number of a file page for display; None when unknown or not a page number."""
    if document.page_labels is None:
        return None
    label = document.page_labels[page - 1].strip()
    return label if label and len(label) <= MAX_LABEL_SHOWN_CHARS else None


# --- The prompt -----------------------------------------------------------------------------


def _toc_block(doc: Doc, nonce: str) -> str:
    lines: list[str] = []
    for section in doc.sections:
        label = _shown_label(doc.source, section.page)
        shown = f"|in {_clean(label, MAX_LABEL_SHOWN_CHARS)}" if label else ""
        lines.append(f"{section.label}|{section.level}|{section.title}|file {section.page}{shown}")
    return wrap_untrusted("toc", "\n".join(lines), nonce, doc=doc.label)


def build_llm_request(
    request: ExtractRequest,
    docs: list[Doc],
    *,
    run_id: uuid.UUID,
    attempt: int,
    nonce: str | None = None,
) -> LlmRequest:
    nonce = nonce or new_nonce()
    prompt = load_prompt()
    parts = [
        wrap_untrusted("description", request.description, nonce),
        wrap_untrusted("today", request.today.isoformat(), nonce),
    ]
    payload_docs: list[dict[str, Any]] = []
    for doc in docs:
        source = doc.source
        progress = f"page_count={source.page_count}"
        if source.last_end_page is not None:
            progress += f"; last_end_page={source.last_end_page}"
        parts.append(wrap_untrusted("document", source.short_name, nonce, doc=doc.label))
        parts.append(wrap_untrusted("progress", progress, nonce, doc=doc.label))
        if doc.sections:
            parts.append(_toc_block(doc, nonce))
        payload_docs.append(
            {
                "label": doc.label,
                "short_name": source.short_name,
                "page_count": source.page_count,
                "last_end_page": source.last_end_page,
                "sections": [{"label": s.label, "title": s.title} for s in doc.sections],
            }
        )
    return LlmRequest(
        task=TASK,
        user_id=request.user_id,
        subject_id=request.subject_id,
        pipeline_run_id=run_id,
        prompt_version=prompt.version,
        attempt=attempt,
        system=prompt.text.replace(_NONCE_PLACEHOLDER, nonce),
        user="\n\n".join(parts),
        output_schema=OUTPUT_SCHEMA,
        payload={
            "description": request.description,
            "today": request.today.isoformat(),
            "documents": payload_docs,
        },
    )


# --- Page references -> file pages ----------------------------------------------------------


class OutputViolation(Exception):
    """The output broke rule `rule` (x1..x9). Carries the rule name only: it is logged."""

    def __init__(self, rule: str) -> None:
        super().__init__(rule)
        self.rule = rule


@dataclass(frozen=True)
class Reference:
    """What the model pointed at, before it is turned into pages."""

    kind: Literal["section", "pages", "continue"]
    from_section: str | None
    to_section: str | None
    basis: Literal["printed", "file"] | None
    from_page: int | None
    to_page: int | None


@dataclass(frozen=True)
class Pages:
    start: int
    end: int
    basis_assumed_file: bool


def _find_section(doc: Doc, label: str | None, *, doc_label: str) -> Section:
    if label is None:
        raise OutputViolation("x4")
    prefix, _, own = label.partition(".")
    if prefix != doc_label or not own:
        raise OutputViolation("x4")  # a section of another document, or no section
    for section in doc.sections:
        if section.label == own:
            return section
    raise OutputViolation("x4")


def _section_end(doc: Doc, section: Section) -> int:
    return section.end


def _printed_to_file(document: ExtractDocument, first: int, last: int) -> tuple[int, int] | None:
    """Both ends from the printed labels, or None (then neither is converted)."""
    labels = document.page_labels
    if labels is None:
        return None

    def positions(number: int) -> list[int]:
        return [
            index + 1
            for index, label in enumerate(labels)
            if label.strip() == str(number) and len(label.strip()) <= MAX_LABEL_SHOWN_CHARS
        ]

    starts = positions(first)
    if not starts:
        return None
    start = starts[0]
    ends = [page for page in positions(last) if page >= start]
    if not ends:
        return None
    return start, ends[0]


def _printed_end(document: ExtractDocument, number: int, start: int) -> int | None:
    """The first file page at or after `start` printed as `number`, or None."""
    labels = document.page_labels
    if labels is None:
        return None
    for index in range(start - 1, len(labels)):
        label = labels[index].strip()
        if label == str(number) and len(label) <= MAX_LABEL_SHOWN_CHARS:
            return index + 1
    return None


def resolve_pages(doc: Doc, reference: Reference) -> Pages:
    """File pages of a reference; raises `OutputViolation` x4 (bad section), x7 (out of range),
    x8 (a "continue" that cannot be worked out). Pure: no I/O."""
    document = doc.source
    assumed = False
    if reference.kind == "section":
        first = _find_section(doc, reference.from_section, doc_label=doc.label)
        last = (
            first
            if reference.to_section is None
            else _find_section(doc, reference.to_section, doc_label=doc.label)
        )
        start, end = first.page, _section_end(doc, last)
    elif reference.kind == "pages":
        if reference.from_page is None or reference.to_page is None or reference.basis is None:
            raise OutputViolation("x4")
        start, end = reference.from_page, reference.to_page
        if reference.basis == "printed":
            converted = _printed_to_file(document, start, end)
            if converted is None:
                assumed = True  # taken as file pages, the card tells the learner to check
            else:
                start, end = converted
    else:  # continue
        if document.last_end_page is None:
            raise OutputViolation("x8")
        start = document.last_end_page + 1
        if reference.to_section is not None:
            end = _section_end(doc, _find_section(doc, reference.to_section, doc_label=doc.label))
        elif reference.to_page is not None and reference.basis is not None:
            end = reference.to_page
            if reference.basis == "printed":
                converted_end = _printed_end(document, reference.to_page, start)
                if converted_end is None:
                    assumed = True
                else:
                    end = converted_end
        else:
            raise OutputViolation("x8")
    if not 1 <= start <= end <= document.page_count:
        raise OutputViolation("x7")
    return Pages(start=start, end=end, basis_assumed_file=assumed)


# --- The rules of the output ----------------------------------------------------------------


class _LlmDay(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    days_ago: int | None
    date: str | None


class _LlmRange(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    doc: str
    kind: Literal["section", "pages", "continue"]
    from_section: str | None
    to_section: str | None
    basis: Literal["printed", "file"] | None
    from_page: int | None
    to_page: int | None
    depth: Depth


class _LlmOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    status: Literal["proposed", "note_only", "clarify"]
    studied_day: _LlmDay
    ranges: list[_LlmRange]
    question: str | None
    reason: ClarifyReason | None
    candidates: list[str]


@dataclass(frozen=True)
class OutcomeRange:
    doc: Doc
    pages: Pages
    depth: Depth


@dataclass(frozen=True)
class Outcome:
    status: Literal["proposed", "note_only", "clarify"]
    studied_on: datetime.date | None
    ranges: list[OutcomeRange]
    question: str | None
    reason: ClarifyReason | None
    candidates: list[Doc]


_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _studied_on(day: _LlmDay, today: datetime.date) -> datetime.date | None:
    if day.days_ago is not None and day.date is not None:
        raise OutputViolation("x5")
    if day.days_ago is not None:
        if not 0 <= day.days_ago <= MAX_STUDIED_DAYS_AGO:
            raise OutputViolation("x5")
        return today - datetime.timedelta(days=day.days_ago)
    if day.date is None:
        return None
    if not _ISO_DATE.match(day.date):
        raise OutputViolation("x5")
    try:
        value = datetime.date.fromisoformat(day.date)
    except ValueError:
        raise OutputViolation("x5") from None
    if not today - datetime.timedelta(days=MAX_STUDIED_DAYS_AGO) <= value <= today:
        raise OutputViolation("x5")
    return value


def check_output(text: str, docs: list[Doc], today: datetime.date) -> Outcome:
    """The rules, in order; the first broken one raises `OutputViolation`.

    x1 schema; x2 the fields fit the status; x3 document labels exist; x4 section labels exist
    in their own document; x5 the day; x6 no range twice; x7 pages inside the document;
    x8 "continue" is workable; x9 the question is one short line.
    """
    try:
        parsed = _LlmOutput.model_validate_json(text)
    except ValidationError:
        raise OutputViolation("x1") from None

    studied = _studied_on(parsed.studied_day, today)  # x5 first: cheap and independent
    has_day = parsed.studied_day.days_ago is not None or parsed.studied_day.date is not None
    # x2
    if parsed.status == "proposed":
        if not 1 <= len(parsed.ranges) <= MAX_RANGES:
            raise OutputViolation("x2")
        if parsed.question is not None or parsed.reason is not None or parsed.candidates:
            raise OutputViolation("x2")
    elif parsed.status == "note_only":
        if parsed.ranges or parsed.question is not None or parsed.reason is not None:
            raise OutputViolation("x2")
        if parsed.candidates:
            raise OutputViolation("x2")
    else:
        if parsed.ranges or has_day or parsed.question is None or parsed.reason is None:
            raise OutputViolation("x2")

    by_label = {doc.label: doc for doc in docs}
    # x3
    if len(parsed.candidates) != len(set(parsed.candidates)) or any(
        label not in by_label for label in parsed.candidates
    ):
        raise OutputViolation("x3")
    ranges: list[OutcomeRange] = []
    seen: set[tuple[str, int, int, str]] = set()
    for item in parsed.ranges:
        doc = by_label.get(item.doc)
        if doc is None:
            raise OutputViolation("x3")
        pages = resolve_pages(
            doc,
            Reference(
                kind=item.kind,
                from_section=item.from_section,
                to_section=item.to_section,
                basis=item.basis,
                from_page=item.from_page,
                to_page=item.to_page,
            ),
        )
        key = (doc.label, pages.start, pages.end, item.depth)
        if key in seen:  # x6
            raise OutputViolation("x6")
        seen.add(key)
        ranges.append(OutcomeRange(doc=doc, pages=pages, depth=item.depth))

    if parsed.status == "clarify":
        question = parsed.question or ""
        if (
            not question.strip()
            or len(question) > MAX_QUESTION_CHARS
            or len(question.splitlines()) != 1
            or question.count("?") + question.count("？") > 1
        ):
            raise OutputViolation("x9")
        if parsed.reason == "ambiguous_document" and len(parsed.candidates) < 2:
            raise OutputViolation("x9")
    return Outcome(
        status=parsed.status,
        studied_on=studied,
        ranges=ranges,
        question=parsed.question,
        reason=parsed.reason,
        candidates=[by_label[label] for label in parsed.candidates],
    )


# --- One run --------------------------------------------------------------------------------


class ExtractInvalidError(Exception):
    """The output broke the rules (twice, or once with no time to ask again): 502."""


def extract_session(
    request: ExtractRequest, *, llm: LlmClient, sessions: SessionFactory
) -> ExtractResponse:
    """Record the run, ask the model (twice at most, while time is left), check, answer."""
    deadline = time.monotonic() + DEADLINE_SECONDS
    prompt = load_prompt()
    run_id = _start_run(sessions, request, prompt)
    try:
        docs = normalize_documents(request)
        response = _ask_model(request, docs, run_id, prompt, llm, deadline)
    except AuditUnavailableError:
        raise
    except ExtractInvalidError:
        _finish_run(sessions, run_id, "extract_invalid")
        raise
    except LlmUnavailableError:
        _finish_run(sessions, run_id, "llm_unavailable")
        raise
    except QuotaExceededError:
        _finish_run(sessions, run_id, "quota_hard_cap")
        raise
    except Exception:
        with suppress(AuditUnavailableError):
            _finish_run(sessions, run_id, "internal_error")
        raise
    _finish_run(sessions, run_id, None)
    return response


def _ask_model(
    request: ExtractRequest,
    docs: list[Doc],
    run_id: uuid.UUID,
    prompt: Prompt,
    llm: LlmClient,
    deadline: float,
) -> ExtractResponse:
    nonce = new_nonce()
    for attempt in (1, 2):
        llm_request = build_llm_request(request, docs, run_id=run_id, attempt=attempt, nonce=nonce)
        result = llm.call(llm_request, deadline=deadline)
        try:
            outcome = check_output(result.text, docs, request.today)
        except OutputViolation as violation:
            _log.warning(
                "extract output refused",
                extra={
                    "outcome": violation.rule,
                    "attempt": attempt,
                    "llm_call_id": str(result.llm_call_id),
                },
            )
            if deadline - time.monotonic() < RETRY_MIN_SECONDS:
                break
            continue
        return _response(outcome, run_id, prompt, result.provider, result.model, result.llm_call_id)
    raise ExtractInvalidError


def _response(
    outcome: Outcome,
    run_id: uuid.UUID,
    prompt: Prompt,
    provider: Literal["anthropic", "fake"],
    model: str,
    call: uuid.UUID,
) -> ExtractResponse:
    common: dict[str, Any] = {
        "provider": provider,
        "model": model,
        "prompt_version": prompt.version,
        "run_id": run_id,
        "llm_call_id": call,
    }
    if outcome.status == "note_only":
        return NoteOnly(studied_on=outcome.studied_on, **common)
    if outcome.status == "clarify":
        assert outcome.question is not None and outcome.reason is not None
        return Clarify(
            question=outcome.question,
            reason=outcome.reason,
            candidate_document_ids=[doc.source.document_id for doc in outcome.candidates],
            **common,
        )
    return Proposed(
        studied_on=outcome.studied_on,
        ranges=[_range(item) for item in outcome.ranges],
        **common,
    )


def _range(item: OutcomeRange) -> ExtractRange:
    source = item.doc.source
    inside = [
        section.title
        for section in item.doc.sections
        if item.pages.start <= section.page <= item.pages.end
    ]
    return ExtractRange(
        document_id=source.document_id,
        start_page=item.pages.start,
        end_page=item.pages.end,
        start_label=_shown_label(source, item.pages.start),
        end_label=_shown_label(source, item.pages.end),
        depth=item.depth,
        sections=inside[:MAX_SECTIONS_PER_RANGE],
        basis_assumed_file=item.pages.basis_assumed_file,
    )


def _start_run(sessions: SessionFactory, request: ExtractRequest, prompt: Prompt) -> uuid.UUID:
    """Committed before any call: no paid call without its run."""
    run = PipelineRun(
        user_id=request.user_id,
        subject_id=request.subject_id,
        task=TASK,
        prompt_version=prompt.version,
        prompt_sha256=prompt.sha256,
    )
    try:
        with sessions() as session:
            session.add(run)
            session.commit()
    except Exception as error:
        _log.exception("pipeline_run not written")
        raise AuditUnavailableError from error
    return run.id


def _finish_run(sessions: SessionFactory, run_id: uuid.UUID, error_code: str | None) -> None:
    try:
        with sessions() as session:
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
    except Exception as error:
        _log.exception("pipeline_run not closed")
        raise AuditUnavailableError from error


# --- The fake extractor (AI_LLM_PROVIDER=fake: local and test only) -------------------------

_PAGES = re.compile(r"(?:tr\.?|trang)\s*(?:file\s*|pdf\s*)?(\d+)\s*(?:-|–|đến|tới)\s*(\d+)")
_UNTIL = re.compile(r"(?:đến|tới|hết)\s*(?:tr\.?|trang)\s*(\d+)")
_CHAPTER = re.compile(r"(?:chương|mục)\s*(\d+(?:\.\d+)?)")
_OUTSIDE = ("qua zalo", "gửi qua", "chưa tải")
_VAGUE = ("một ít", "một chút", "sơ sơ")


def _norm(text: str) -> str:
    return unicodedata.normalize("NFC", text).casefold()


def _depth_of(clause: str) -> str:
    if "chưa hiểu" in clause or "mơ hồ" in clause:
        return "unclear"
    if "lướt" in clause or "xem qua" in clause:
        return "skim"
    return "deep"


def _clarify(question: str, reason: str, candidates: list[str]) -> str:
    return json.dumps(
        {
            "status": "clarify",
            "studied_day": {"days_ago": None, "date": None},
            "ranges": [],
            "question": question,
            "reason": reason,
            "candidates": candidates,
        },
        ensure_ascii=False,
    )


def fake_extract(request: LlmRequest) -> str:
    """A deterministic extraction from keywords, shaped like a model's output (PLAN T4.10).

    It proves the data flow and the code's checks, not the quality of a real model (T4.11
    measures that). Its output goes through the same rules as a model's.
    """
    payload = request.payload
    description = _norm(payload["description"])
    docs: list[dict[str, Any]] = payload["documents"]

    day: dict[str, int | None] = {"days_ago": None, "date": None}
    for phrase, ago in (("hôm kia", 2), ("hôm qua", 1), ("hôm nay", 0), ("tối nay", 0)):
        if phrase in description:
            day["days_ago"] = ago
            break

    def mentioned(clause: str) -> list[dict[str, Any]]:
        return [doc for doc in docs if _norm(doc["short_name"]) in clause]

    all_mentioned = mentioned(description)
    if any(phrase in description for phrase in _VAGUE):
        return _clarify(
            "Bạn học khoảng trang nào?", "ambiguous_range", [d["label"] for d in all_mentioned]
        )
    if not all_mentioned and any(phrase in description for phrase in _OUTSIDE):
        return _clarify(
            "Tài liệu này chưa có trong môn, bạn tải lên được không?", "unknown_document", []
        )
    if len(all_mentioned) > 1 and not _PAGES.search(description):
        return _clarify(
            "Bạn học tài liệu nào?", "ambiguous_document", [d["label"] for d in all_mentioned]
        )

    ranges: list[dict[str, Any]] = []
    previous: dict[str, Any] | None = None
    for raw in re.split(r"[,;]| kèm | và ", description):
        clause = raw.strip()
        found = mentioned(clause)
        doc = found[0] if found else previous or (docs[0] if len(docs) == 1 else None)
        if found:
            previous = found[0]
        base: dict[str, Any] = {
            "from_section": None,
            "to_section": None,
            "basis": None,
            "from_page": None,
            "to_page": None,
            "depth": _depth_of(clause),
        }
        pages = _PAGES.search(clause)
        until = _UNTIL.search(clause)
        chapter = _CHAPTER.search(clause)
        if doc is None:
            continue
        basis = "file" if "trang file" in clause or "trang pdf" in clause else "printed"
        if "học tiếp" in clause and until:
            ranges.append(
                {
                    **base,
                    "doc": doc["label"],
                    "kind": "continue",
                    "basis": basis,
                    "to_page": int(until.group(1)),
                }
            )
        elif pages:
            ranges.append(
                {
                    **base,
                    "doc": doc["label"],
                    "kind": "pages",
                    "basis": basis,
                    "from_page": int(pages.group(1)),
                    "to_page": int(pages.group(2)),
                }
            )
        elif chapter:
            number = chapter.group(1)
            hit = next(
                (
                    s
                    for s in doc["sections"]
                    if _norm(s["title"]).startswith(
                        (f"chương {number}", f"{number} ", f"{number}.")
                    )
                ),
                None,
            )
            if hit is None:
                return _clarify(
                    "Bạn học mục nào trong tài liệu?", "ambiguous_range", [doc["label"]]
                )
            ranges.append(
                {
                    **base,
                    "doc": doc["label"],
                    "kind": "section",
                    "from_section": f"{doc['label']}.{hit['label']}",
                }
            )
    if "học tiếp" in description and not ranges:
        return _clarify("Bạn học tiếp đến trang nào?", "missing_info", [d["label"] for d in docs])
    if not ranges:
        return json.dumps(
            {
                "status": "note_only",
                "studied_day": day,
                "ranges": [],
                "question": None,
                "reason": None,
                "candidates": [],
            },
            ensure_ascii=False,
        )
    return json.dumps(
        {
            "status": "proposed",
            "studied_day": day,
            "ranges": ranges,
            "question": None,
            "reason": None,
            "candidates": [],
        },
        ensure_ascii=False,
    )
