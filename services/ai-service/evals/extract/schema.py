"""The eval dataset for /v1/extract-session (US-02 AC6): one JSON case per line.

A case holds what a learner said, the documents of the subject (named books from
`fixtures.BOOKS`, with a table of contents shaped like T4.7's) and the label a person gave it.
The checks here keep a wrong label from reaching a run: a mislabelled case measures nothing.
"""

import datetime
import json
import uuid
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from ai_service.tasks.extract_models import (
    ClarifyReason,
    Depth,
    ExtractDocument,
    ExtractRequest,
    TocEntry,
)
from evals.extract.fixtures import BOOKS

# The learner's date in every case, so "hôm qua" always means the same day.
EVAL_TODAY = datetime.date(2026, 10, 28)

Category = Literal[
    "section",
    "pages_printed",
    "pages_file",
    "continue",
    "multi_range",
    "mixed_lang",
    "typo",
    "day",
    "note_only",
    "clarify",
]
Status = Literal["proposed", "note_only", "clarify"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CaseDoc(_Strict):
    book: str
    last_end_page: int | None = Field(default=None, ge=1)


class ExpectedRange(_Strict):
    doc: int = Field(ge=0)  # index in the case's `docs`
    start: int = Field(ge=1)  # FILE pages
    end: int = Field(ge=1)
    depth: Depth = "deep"
    assumed_file: bool = False  # printed numbers that cannot be mapped, taken as file pages


class Expected(_Strict):
    status: Status
    days_ago: int | None = Field(default=None, ge=0)
    ranges: list[ExpectedRange] = Field(default_factory=list[ExpectedRange])
    reason: ClarifyReason | None = None
    candidates: list[int] | None = None  # doc indexes; checked only when given


class ExtractCase(_Strict):
    id: str = Field(min_length=1)
    category: Category
    description: str = Field(min_length=1, max_length=2000)
    docs: list[CaseDoc] = Field(min_length=1, max_length=12)
    expected: Expected

    @model_validator(mode="after")
    def _label_is_consistent(self) -> Self:
        for doc in self.docs:
            if doc.book not in BOOKS:
                raise ValueError(f"unknown book {doc.book}")
            if doc.last_end_page is not None and doc.last_end_page > BOOKS[doc.book].page_count:
                raise ValueError("last_end_page beyond the book")
        expected = self.expected
        if expected.status == "proposed":
            if not expected.ranges or expected.reason is not None:
                raise ValueError("a proposed case needs ranges and no reason")
        elif expected.ranges:
            raise ValueError(f"a {expected.status} case has no ranges")
        if expected.status == "clarify":
            if expected.reason is None or expected.days_ago is not None:
                raise ValueError("a clarify case needs a reason and no day")
        elif expected.reason is not None or expected.candidates is not None:
            raise ValueError(f"a {expected.status} case has no reason or candidates")
        for item in expected.ranges:
            if item.doc >= len(self.docs):
                raise ValueError("range names a doc that is not in docs")
            if not 1 <= item.start <= item.end:
                raise ValueError("range must have 1 <= start <= end")
            if item.end > BOOKS[self.docs[item.doc].book].page_count:
                raise ValueError("range ends beyond the book")
        if any(not 0 <= index < len(self.docs) for index in expected.candidates or []):
            raise ValueError("candidate is not a doc index")
        return self


def _id(case: ExtractCase, *parts: object) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, "/".join(["essity-eval", case.id, *map(str, parts)]))


def build_request(case: ExtractCase) -> ExtractRequest:
    """The request core-api would send for this case."""
    documents: list[ExtractDocument] = []
    for index, doc in enumerate(case.docs):
        book = BOOKS[doc.book]
        documents.append(
            ExtractDocument(
                document_id=_id(case, "doc", index),
                short_name=book.short_name,
                page_count=book.page_count,
                page_labels=book.page_labels(),
                toc=[TocEntry(title=t, level=lv, page=p) for t, lv, p in book.toc],
                last_end_page=doc.last_end_page,
            )
        )
    return ExtractRequest(
        user_id=_id(case, "user"),
        subject_id=_id(case, "subject"),
        description=case.description,
        today=EVAL_TODAY,
        documents=documents,
    )


def load_cases(path: Path) -> list[ExtractCase]:
    cases: list[ExtractCase] = []
    seen: set[str] = set()
    for number, line in enumerate(path.read_text("utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            case = ExtractCase.model_validate(json.loads(line))
        except (ValidationError, json.JSONDecodeError) as error:
            raise ValueError(f"{path.name} line {number}: {error_reason(error)}") from None
        if case.id in seen:
            raise ValueError(f"{path.name} line {number}: duplicate id {case.id}")
        seen.add(case.id)
        cases.append(case)
    return cases


def error_reason(error: ValidationError | json.JSONDecodeError) -> str:
    # Never echo the input: a case may hold a learner's text.
    if isinstance(error, json.JSONDecodeError):
        return "not valid JSON"
    return "; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in error.errors())
