"""The /v1/extract-session contract (T4.10, US-02). core-api (T4.12) is the only caller.

The request carries what T4.7 wrote for each document of the subject, as it is: `toc` is
`toc.json`'s entries and `page_labels` is `page_labels.json`'s list (title up to 500 characters
and possibly empty, level from 0, up to 16 deep, labels possibly empty). ai-service normalizes it
(`extract_session.normalize_documents`), so a real PDF is never a 422.

The answer is a union on `status`: `proposed` (ranges, in FILE pages), `note_only` (nothing to
read from a document: US-02 AC10) or `clarify` (exactly one question: AC5).
"""

import datetime
import re
import uuid
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

from ai_service.tasks.grade_models import NoNul, Provider

MAX_DESCRIPTION_CHARS = 2000
MAX_DOCUMENTS = 12
MAX_PAGES = 5000
MAX_TOC_ENTRIES = 5000
MAX_TOC_ENTRIES_TOTAL = 6000
MAX_TOC_TITLE_CHARS = 500
MAX_LABEL_CHARS = 128
MAX_SHORT_NAME_CHARS = 100
MAX_RANGES = 6
MAX_QUESTION_CHARS = 300
MAX_SECTIONS_PER_RANGE = 10

Depth = Literal["deep", "skim", "unclear"]
ClarifyReason = Literal["ambiguous_document", "ambiguous_range", "unknown_document", "missing_info"]


def _not_blank(text: str) -> str:
    if not text.strip():
        raise ValueError("must not be blank")
    return text


def _one_line(text: str) -> str:
    # Whitespace of any kind becomes one space: a name cannot add a line of its own.
    return re.sub(r"\s+", " ", text).strip()


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


Description = Annotated[
    str, Field(min_length=1, max_length=MAX_DESCRIPTION_CHARS), AfterValidator(_not_blank), NoNul
]
ShortName = Annotated[
    str,
    Field(min_length=1, max_length=MAX_SHORT_NAME_CHARS),
    AfterValidator(_not_blank),
    NoNul,
    AfterValidator(_one_line),
]


class TocEntry(_Strict):
    title: Annotated[str, Field(max_length=MAX_TOC_TITLE_CHARS), NoNul]
    level: int = Field(ge=0, le=16)
    # 1-based FILE page, or None when the bookmark points nowhere usable (T4.7).
    page: int | None = Field(ge=1, le=MAX_PAGES)


class ExtractDocument(_Strict):
    document_id: uuid.UUID
    short_name: ShortName
    page_count: int = Field(ge=1, le=MAX_PAGES)
    # The printed number of each file page (T4.7 `page_labels.json`), or None.
    page_labels: list[Annotated[str, Field(max_length=MAX_LABEL_CHARS), NoNul]] | None
    toc: list[TocEntry] = Field(max_length=MAX_TOC_ENTRIES)
    # Last FILE page of the previous session on this document, for "học tiếp".
    last_end_page: int | None = Field(ge=1, le=MAX_PAGES)

    @model_validator(mode="after")
    def _consistent(self) -> "ExtractDocument":
        if self.page_labels is not None and len(self.page_labels) != self.page_count:
            raise ValueError("page_labels must have one label per page")
        if any(entry.page is not None and entry.page > self.page_count for entry in self.toc):
            raise ValueError("toc page beyond page_count")
        if self.last_end_page is not None and self.last_end_page > self.page_count:
            raise ValueError("last_end_page beyond page_count")
        return self


class ExtractRequest(_Strict):
    user_id: uuid.UUID
    subject_id: uuid.UUID
    description: Description
    # The learner's date today (core works it out in the learner's time zone).
    today: datetime.date
    documents: list[ExtractDocument] = Field(min_length=1, max_length=MAX_DOCUMENTS)

    @model_validator(mode="after")
    def _consistent(self) -> "ExtractRequest":
        ids = [document.document_id for document in self.documents]
        if len(ids) != len(set(ids)):
            raise ValueError("document_id must be unique")
        if sum(len(document.toc) for document in self.documents) > MAX_TOC_ENTRIES_TOTAL:
            raise ValueError("too many toc entries in all")
        return self


# --- Response -------------------------------------------------------------------------------


class _Common(_Strict):
    provider: Provider
    model: str | None
    prompt_version: str
    run_id: uuid.UUID
    llm_call_id: uuid.UUID | None


class ExtractRange(_Strict):
    document_id: uuid.UUID
    # FILE pages, 1-based: what the page images and `session_range` use. `start_label` and
    # `end_label` are the printed numbers for the confirmation card (None: none known).
    start_page: int
    end_page: int
    start_label: str | None
    end_label: str | None
    depth: Depth
    # Titles of the document's sections inside the range, from its table of contents.
    sections: list[str]
    # True when the learner's printed numbers could not be mapped and were taken as file pages:
    # the card must tell the learner to check them.
    basis_assumed_file: bool


class Proposed(_Common):
    status: Literal["proposed"] = "proposed"
    # None: the learner did not say; core uses today.
    studied_on: datetime.date | None
    ranges: list[ExtractRange]


class NoteOnly(_Common):
    status: Literal["note_only"] = "note_only"
    studied_on: datetime.date | None


class Clarify(_Common):
    status: Literal["clarify"] = "clarify"
    question: str
    reason: ClarifyReason
    candidate_document_ids: list[uuid.UUID]


ExtractResponse = Annotated[Proposed | NoteOnly | Clarify, Field(discriminator="status")]
