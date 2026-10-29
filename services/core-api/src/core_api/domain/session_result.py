"""The result file of a processed session (session-result.v1, T4.17), read as untrusted data.

ai-service wrote it from an LLM's output, so nothing in it is trusted: it is parsed against a closed
model (a file that breaks the contract is refused whole), then cleaned item by item. A unit, an
anchor or a question that breaks a rule is dropped and counted, never stored; one bad item does not
cost the learner the session. Cleaning is pure: it knows no database. The handler checks what needs
one (the units of `merges` and `lineage`, the questions already stored).

Strings lose NUL and lone surrogates (Postgres refuses both) and are never logged (ADR-0013).
"""

import re
import uuid
from collections.abc import Collection
from dataclasses import dataclass, field
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

# `knowledge_unit.title` is String(200).
TITLE_MAX = 200
# Level 1 and 2 ask about one unit; level 3 joins two or more (us-04b AC1).
LEVEL_SINGLE = (1, 2)
LEVEL_JOIN = 3

_UNSAFE = re.compile("[\x00\ud800-\udfff]")


class ResultRefused(Exception):
    """The file is well formed but is not this session's, or holds one unit twice."""


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class FileAnchor(_Closed):
    source: Literal["document", "notes"]
    document_id: uuid.UUID | None
    page_no: Annotated[int, Field(ge=1)] | None
    start: Annotated[int, Field(ge=0)]
    end: Annotated[int, Field(ge=0)]
    quote_text: str


class FileUnit(_Closed):
    unit_id: uuid.UUID
    title: Annotated[str, Field(min_length=1)]
    summary: str
    kind: Literal["concept", "mechanism", "comparison", "formula", "example"]
    section_id: uuid.UUID | None
    lineage: list[uuid.UUID]
    single_source: bool
    anchors: Annotated[list[FileAnchor], Field(min_length=1)]


class FileMerge(_Closed):
    existing_unit_id: uuid.UUID
    anchors: Annotated[list[FileAnchor], Field(min_length=1)]


class FileQuestion(_Closed):
    unit_ids: Annotated[list[uuid.UUID], Field(min_length=1)]
    level: Literal[1, 2, 3]
    prompt: Annotated[str, Field(min_length=1)]
    reference_answer: Annotated[str, Field(min_length=1)]
    rubric: Annotated[str, Field(min_length=1)]


class _Counts(_Closed):
    anchors: Annotated[int, Field(ge=0)]
    units: Annotated[int, Field(ge=0)]
    questions: Annotated[int, Field(ge=0)]


class _Skipped(_Closed):
    kind: Literal["page", "note"]
    ref: Annotated[int, Field(ge=0)]
    reason: Literal["no_text", "truncated", "needs_ocr", "unreadable"]


class SessionResultFile(_Closed):
    version: Literal[1]
    study_session_id: uuid.UUID
    units: list[FileUnit]
    merges: list[FileMerge]
    questions: list[FileQuestion]
    dropped: _Counts
    skipped: list[_Skipped]


def parse_result(raw: bytes) -> SessionResultFile:
    """The file against the contract. Raises `pydantic.ValidationError` (its errors echo the input:
    never log them)."""
    return SessionResultFile.model_validate_json(raw)


@dataclass(frozen=True)
class CleanAnchor:
    source: str
    document_id: uuid.UUID | None
    page_no: int | None
    start: int
    end: int
    quote_text: str


@dataclass(frozen=True)
class CleanUnit:
    unit_id: uuid.UUID
    title: str
    summary: str
    kind: str
    section_id: None  # no `doc_section` table yet: NULL until there is (plan T4.17)
    lineage: tuple[uuid.UUID, ...]
    anchors: tuple[CleanAnchor, ...]


@dataclass(frozen=True)
class CleanMerge:
    existing_unit_id: uuid.UUID
    anchors: tuple[CleanAnchor, ...]


@dataclass(frozen=True)
class CleanQuestion:
    unit_ids: tuple[uuid.UUID, ...]
    level: int
    prompt: str
    reference_answer: str
    rubric: str


@dataclass
class CleanResult:
    units: list[CleanUnit] = field(default_factory=list[CleanUnit])
    merges: list[CleanMerge] = field(default_factory=list[CleanMerge])
    questions: list[CleanQuestion] = field(default_factory=list[CleanQuestion])
    dropped_anchors: int = 0
    dropped_units: int = 0
    dropped_questions: int = 0


def text_of(value: str) -> str:
    """The string without what Postgres refuses (NUL, lone surrogates)."""
    return _UNSAFE.sub("", value)


def clean(
    parsed: SessionResultFile, *, study_session_id: uuid.UUID, documents: Collection[uuid.UUID]
) -> CleanResult:
    """Keep what is sound. `documents` are the ids of the session's subject's documents of this
    user. Raises `ResultRefused` for a file that is not this session's or repeats a unit id."""
    if parsed.study_session_id != study_session_id:
        raise ResultRefused("study_session_id")
    ids = [u.unit_id for u in parsed.units]
    if len(set(ids)) != len(ids):
        raise ResultRefused("duplicate_unit_id")
    out = CleanResult()
    for item in parsed.units:
        title = text_of(item.title)[:TITLE_MAX].strip()
        anchors = _anchors(item.anchors, documents, out)
        if not title or not anchors:
            out.dropped_units += 1
            continue
        out.units.append(
            CleanUnit(
                unit_id=item.unit_id,
                title=title,
                summary=text_of(item.summary),
                kind=item.kind,
                section_id=None,
                lineage=tuple(dict.fromkeys(item.lineage)),
                anchors=anchors,
            )
        )
    for merge in parsed.merges:
        anchors = _anchors(merge.anchors, documents, out)
        if anchors:
            out.merges.append(CleanMerge(merge.existing_unit_id, anchors))
    kept = {u.unit_id for u in out.units}
    for question in parsed.questions:
        kept_question = _question(question, kept)
        if kept_question is None:
            out.dropped_questions += 1
        else:
            out.questions.append(kept_question)
    return out


def _anchors(
    anchors: list[FileAnchor], documents: Collection[uuid.UUID], out: CleanResult
) -> tuple[CleanAnchor, ...]:
    kept: list[CleanAnchor] = []
    for anchor in anchors:
        quote = text_of(anchor.quote_text)
        if anchor.source == "document":
            sound = anchor.document_id in documents and anchor.page_no is not None
        else:
            sound = anchor.document_id is None
        if not sound or anchor.start > anchor.end or not quote.strip():
            out.dropped_anchors += 1
            continue
        kept.append(
            CleanAnchor(
                anchor.source, anchor.document_id, anchor.page_no, anchor.start, anchor.end, quote
            )
        )
    return tuple(kept)


def _question(question: FileQuestion, kept: set[uuid.UUID]) -> CleanQuestion | None:
    prompt, answer, rubric = (
        text_of(question.prompt).strip(),
        text_of(question.reference_answer).strip(),
        text_of(question.rubric).strip(),
    )
    units = tuple(dict.fromkeys(question.unit_ids))
    if not (prompt and answer and rubric) or not kept.issuperset(units):
        return None
    if question.level in LEVEL_SINGLE and len(units) != 1:
        return None
    if question.level == LEVEL_JOIN and len(units) < 2:
        return None
    return CleanQuestion(units, question.level, prompt, answer, rubric)
