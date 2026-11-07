"""Splitting text into knowledge units and anchoring them (T4.15, US-02b).

The core is pure: `chunk_units(request, ask)` where `ask` sends a `ChunkPrompt` to the model and
returns its text. T4.16 binds `ask` to `LlmClient` and the quota guard; tests bind it to a fake.

- Untrusted text (pages, notes, unit titles and summaries, document names) enters the prompt only
  through `wrap_untrusted` (escaped, nonce-tagged block). The model sees labels (`D1.p3`,
  `notes`, `U2`), never ids.
- The model never gives offsets. For each quote the CODE looks it up in the text of the page
  the model named (`anchor_check.find_quote`); the anchor is `original[start:end]`. Anchors not
  found are dropped, a unit left without an anchor is dropped (AC3). Rules refuse by name only:
  no source text reaches an exception, a log or `Dropped` (ADR-0013).
- `merge_into: "U<n>"` only suggests a duplicate: the code maps it to an existing unit and
  emits anchors to ADD. An existing unit is never changed or removed (AC4, ARCH §12).
"""

import hashlib
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ai_service.domain.anchor_check import find_quote, normalize_with_map, unescape_quote
from ai_service.llm.system import render_system
from ai_service.tasks.chunk_models import (
    MAX_OUTPUT_CHARS,
    MAX_QUOTE_CHARS,
    MAX_TITLE_WORDS,
    MAX_UNITS_OUT,
    Anchor,
    AnchorAddition,
    ChunkRequest,
    ChunkResult,
    Dropped,
    LlmAnchor,
    LlmChunks,
    LlmUnit,
    NewUnit,
)
from ai_service.tasks.grade import new_nonce, wrap_untrusted

_log = logging.getLogger(__name__)

TASK = "chunk_units"
PROMPT_VERSION = "v3"
_PROMPTS = Path(__file__).resolve().parents[3] / "prompts"

MAX_PAGES = 60
MAX_PAGE_CHARS = 20_000
MAX_NOTES_CHARS = 8_000
MAX_TOTAL_CHARS = 200_000
MAX_EXISTING = 200
MAX_DOCUMENTS = 20
MAX_DOC_NAME_CHARS = 300
PROMPT_TITLE_CHARS = 120
PROMPT_SUMMARY_CHARS = 300
ATTEMPTS = 2

OUTPUT_SCHEMA: dict[str, Any] = LlmChunks.model_json_schema()


class ChunkInputError(Exception):
    """The request cannot be chunked as it is. Carries the rule name only."""

    def __init__(self, rule: str) -> None:
        super().__init__(rule)
        self.rule = rule


class ChunkInputTooLarge(ChunkInputError):
    """Over a size limit: refused, never cut silently (T4.16 splits into batches)."""


class OutputCut(ChunkInputError):
    """The model's answer was cut at the output cap (`stop_reason=max_tokens`): asking the same
    again gives the same cut, so the caller halves the input instead (FIX-CHUNK)."""

    def __init__(self) -> None:
        super().__init__("output_cut")


class ChunkInvalidError(Exception):
    """The model broke the output rules on every attempt."""


class OutputViolation(Exception):
    """The output broke rule `rule`. Carries the rule name and, for `schema`, where and why
    (`error_shape`): both are logged, never the text."""

    def __init__(self, rule: str, errors: list[dict[str, Any]] | None = None) -> None:
        super().__init__(rule)
        self.rule = rule
        self.errors = errors


class _Envelope(BaseModel):
    """The answer's outer shape; each unit is checked on its own (`LlmUnit`)."""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    units: Annotated[list[dict[str, Any]], Field(max_length=MAX_UNITS_OUT)]


@dataclass(frozen=True)
class ChunkPrompt:
    system: str
    user: str
    output_schema: dict[str, Any]
    nonce: str


@dataclass(frozen=True)
class Prompt:
    version: str
    text: str
    sha256: str


@lru_cache
def load_prompt(version: str = PROMPT_VERSION) -> Prompt:
    text = (_PROMPTS / TASK / f"{version}.md").read_text("utf-8")
    return Prompt(version=version, text=text, sha256=hashlib.sha256(text.encode()).hexdigest())


# --- Labels ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class _Source:
    kind: str  # "document" | "notes"
    document_id: uuid.UUID | None
    page_no: int | None
    text: str


@dataclass(frozen=True)
class Labels:
    """What the model may name: label -> source text, label -> existing unit id."""

    sources: dict[str, _Source]
    units: dict[str, uuid.UUID]
    titles: dict[str, uuid.UUID]  # normalized title -> existing unit id (first wins)


def _fold(text: str) -> str:
    return normalize_with_map(text)[0].strip().casefold()


def _labels(request: ChunkRequest) -> Labels:
    sources: dict[str, _Source] = {}
    for d, doc in enumerate(request.documents, start=1):
        for page in doc.pages:
            label = f"D{d}.p{page.page_no}"
            if label in sources:
                raise ChunkInputError("duplicate_page")
            sources[label] = _Source("document", doc.document_id, page.page_no, page.text)
    if request.notes_text is not None:
        sources["notes"] = _Source("notes", None, None, request.notes_text)
    units: dict[str, uuid.UUID] = {}
    titles: dict[str, uuid.UUID] = {}
    for n, existing in enumerate(request.existing_units, start=1):
        units[f"U{n}"] = existing.unit_id
        titles.setdefault(_fold(existing.title), existing.unit_id)
    return Labels(sources, units, titles)


def _check_limits(request: ChunkRequest) -> None:
    pages = [p for doc in request.documents for p in doc.pages]
    notes = request.notes_text or ""
    if len(request.documents) > MAX_DOCUMENTS:
        raise ChunkInputTooLarge("documents")
    if any(len(d.name) > MAX_DOC_NAME_CHARS for d in request.documents):
        raise ChunkInputTooLarge("doc_name")
    if len(pages) > MAX_PAGES:
        raise ChunkInputTooLarge("pages")
    if any(len(p.text) > MAX_PAGE_CHARS for p in pages):
        raise ChunkInputTooLarge("page_chars")
    if len(notes) > MAX_NOTES_CHARS:
        raise ChunkInputTooLarge("notes_chars")
    if sum(len(p.text) for p in pages) + len(notes) > MAX_TOTAL_CHARS:
        raise ChunkInputTooLarge("total_chars")
    if len(request.existing_units) > MAX_EXISTING:
        raise ChunkInputTooLarge("existing_units")


# --- Prompt ---------------------------------------------------------------------------------


def _all_text(request: ChunkRequest) -> str:
    parts = [request.notes_text or ""]
    for doc in request.documents:
        parts.append(doc.name)
        parts.extend(p.text for p in doc.pages)
    for unit in request.existing_units:
        parts.extend((unit.title, unit.summary))
    return "\n".join(parts)


def build_prompt(request: ChunkRequest) -> ChunkPrompt:
    corpus = _all_text(request)
    nonce = new_nonce()
    while nonce in corpus:
        nonce = new_nonce()
    blocks: list[str] = []
    for d, doc in enumerate(request.documents, start=1):
        blocks.append(wrap_untrusted("document_name", doc.name, nonce, label=f"D{d}"))
        for page in doc.pages:
            label = f"D{d}.p{page.page_no}"
            blocks.append(wrap_untrusted("page", page.text, nonce, label=label))
    if request.notes_text is not None:
        blocks.append(wrap_untrusted("notes", request.notes_text, nonce, label="notes"))
    for n, unit in enumerate(request.existing_units, start=1):
        text = f"{unit.title[:PROMPT_TITLE_CHARS]}\n{unit.summary[:PROMPT_SUMMARY_CHARS]}"
        blocks.append(wrap_untrusted("existing_unit", text, nonce, label=f"U{n}"))
    system = render_system(load_prompt().text, nonce)
    return ChunkPrompt(system, "\n\n".join(blocks), OUTPUT_SCHEMA, nonce)


# --- Output check ---------------------------------------------------------------------------


def _anchor_key(a: Anchor) -> tuple[object, ...]:
    return (a.source, a.document_id, a.page_no, a.start, a.end)


def _resolve_anchors(unit: LlmUnit, labels: Labels, dropped: list[Dropped]) -> list[Anchor]:
    found: dict[tuple[object, ...], Anchor] = {}
    for item in unit.anchors:
        source = labels.sources.get(item.page)
        if source is None:
            dropped.append(Dropped(kind="anchor", reason="unknown_page"))
            continue
        quote = unescape_quote(item.quote)
        if len(quote.strip()) > MAX_QUOTE_CHARS:
            dropped.append(Dropped(kind="anchor", reason="quote_too_long"))
            continue
        span = find_quote(source.text, quote)
        if span is None:
            dropped.append(Dropped(kind="anchor", reason="quote_not_found"))
            continue
        start, end = span
        anchor = Anchor(
            source="notes" if source.kind == "notes" else "document",
            document_id=source.document_id,
            page_no=source.page_no,
            start=start,
            end=end,
            quote_text=source.text[start:end],
        )
        found.setdefault(_anchor_key(anchor), anchor)
    return list(found.values())


_KNOWN_KEYS = (
    frozenset(LlmChunks.model_fields)
    | frozenset(LlmUnit.model_fields)
    | frozenset(LlmAnchor.model_fields)
)


def error_shape(error: ValidationError) -> list[dict[str, Any]]:
    """Where and why pydantic refused, never what: positions and known field names only. A key
    the model made up is model text, so it becomes "?" (ADR-0013)."""
    return [
        {
            "loc": [p if isinstance(p, int) or p in _KNOWN_KEYS else "?" for p in e["loc"]],
            "type": e["type"],
        }
        for e in error.errors(include_input=False, include_url=False, include_context=False)
    ]


def _units(text: str, dropped: list[Dropped]) -> list[LlmUnit]:
    """The units of the answer. The envelope (JSON, `units` list, its length) is all or nothing;
    a unit that breaks a rule of its own is dropped by rule name and the rest kept (FIX-CHUNK).
    An answer whose every unit broke a rule raises, so the call is tried again."""
    try:
        envelope = _Envelope.model_validate_json(text)
    except ValidationError as error:
        raise OutputViolation("schema", error_shape(error)) from None  # never carries the text
    units: list[LlmUnit] = []
    first_rule: str | None = None
    for raw in envelope.units:
        try:
            unit = LlmUnit.model_validate(raw)
        except ValidationError as error:
            _log.warning(
                "chunk unit dropped",
                extra={"outcome": "schema", "schema_errors": error_shape(error)},
            )
            dropped.append(Dropped(kind="unit", reason="schema"))
            first_rule = first_rule or "schema"
            continue
        if len(unit.title.split()) > MAX_TITLE_WORDS:
            dropped.append(Dropped(kind="unit", reason="title_words"))
            first_rule = first_rule or "title_words"
            continue
        units.append(unit)
    if first_rule is not None and not units:
        raise OutputViolation(first_rule)
    return units


def check_output(text: str, labels: Labels) -> ChunkResult:
    """Parse and verify the model's text. A broken envelope raises `OutputViolation`."""
    if len(text) > MAX_OUTPUT_CHARS:
        raise OutputViolation("too_long")
    dropped: list[Dropped] = []
    units = _units(text, dropped)

    new_units: list[NewUnit] = []
    merges: dict[uuid.UUID, dict[tuple[object, ...], Anchor]] = {}
    new_by_title: dict[str, dict[tuple[object, ...], Anchor]] = {}
    for unit in units:
        anchors = _resolve_anchors(unit, labels, dropped)
        if not anchors:
            dropped.append(Dropped(kind="unit", reason="no_valid_anchor"))
            continue
        target = labels.units.get(unit.merge_into or "") or labels.titles.get(_fold(unit.title))
        if target is not None:
            bucket = merges.setdefault(target, {})
            for anchor in anchors:
                bucket.setdefault(_anchor_key(anchor), anchor)
            continue
        folded = _fold(unit.title)
        if folded in new_by_title:  # same title twice in one call: one unit, anchors united
            for anchor in anchors:
                new_by_title[folded].setdefault(_anchor_key(anchor), anchor)
            continue
        new_by_title[folded] = {_anchor_key(a): a for a in anchors}
        lineage: list[uuid.UUID] = []
        for label in unit.lineage:
            known = labels.units.get(label)
            if known is not None and known not in lineage:
                lineage.append(known)
        new_units.append(
            NewUnit(
                title=unit.title.strip(),
                summary=unit.summary.strip(),
                kind=unit.kind,
                lineage=lineage,
                single_source=len({a.source for a in anchors}) == 1,
                anchors=anchors,
            )
        )
    for folded, anchor_map in new_by_title.items():
        merged = list(anchor_map.values())
        index = next(i for i, u in enumerate(new_units) if _fold(u.title) == folded)
        new_units[index] = new_units[index].model_copy(
            update={"anchors": merged, "single_source": len({a.source for a in merged}) == 1}
        )
    return ChunkResult(
        new_units=new_units,
        merges=[
            AnchorAddition(existing_unit_id=k, anchors=list(v.values())) for k, v in merges.items()
        ],
        dropped=dropped,
    )


# --- Entry point ----------------------------------------------------------------------------


def chunk_units(request: ChunkRequest, ask: Callable[[ChunkPrompt], str]) -> ChunkResult:
    """New units (one idea each, anchored), plus anchors to add to existing units."""
    _check_limits(request)
    labels = _labels(request)
    if not any(s.text.strip() for s in labels.sources.values()):
        return ChunkResult(new_units=[], merges=[], dropped=[])
    prompt = build_prompt(request)
    for attempt in range(1, ATTEMPTS + 1):
        try:
            return check_output(ask(prompt), labels)
        except OutputViolation as violation:
            _log.warning(
                "chunk output refused",
                extra={
                    "outcome": violation.rule,
                    "attempt": attempt,
                    "schema_errors": violation.errors,
                },
            )
    raise ChunkInvalidError
