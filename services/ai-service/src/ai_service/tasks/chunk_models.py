"""Models of the chunking core (T4.15, US-02b): input, what the model may say, result.

The core takes TEXT: document page text, the learner's typed notes, the units that already exist.
Photo-to-text plugs in later (T4.14). The output carries `lineage` and `section_id`, which T4.17
persists (`unit_lineage`, `knowledge_unit.section_id`); T4.15 makes no migration.

Offsets are Python code points into the original text, `end` exclusive.
"""

import uuid
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

Kind = Literal["concept", "mechanism", "comparison", "formula", "example"]
Source = Literal["document", "notes"]

MAX_UNITS_OUT = 40
MAX_ANCHORS_PER_UNIT = 6
MAX_TITLE_WORDS = 10
MAX_SUMMARY_CHARS = 600
MAX_QUOTE_CHARS = 300  # longer quotes drop that anchor only
MAX_OUTPUT_CHARS = 60_000


def _no_nul(text: str) -> str:
    if "\x00" in text:
        raise ValueError("NUL")
    return text


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


class PageInput(_Strict):
    page_no: Annotated[int, Field(ge=1)]
    text: Annotated[str, AfterValidator(_no_nul)]


class DocInput(_Strict):
    document_id: uuid.UUID
    name: Annotated[str, AfterValidator(_no_nul)]
    pages: list[PageInput]


class ExistingUnit(_Strict):
    unit_id: uuid.UUID
    title: Annotated[str, AfterValidator(_no_nul)]
    summary: Annotated[str, AfterValidator(_no_nul)]


class ChunkRequest(_Strict):
    documents: list[DocInput] = []
    notes_text: Annotated[str, AfterValidator(_no_nul)] | None = None
    existing_units: list[ExistingUnit] = []


# --- What the model may say (checked by `check_output`) -------------------------------------


class LlmAnchor(_Strict):
    page: str  # "D1.p3" or "notes"
    quote: Annotated[str, Field(max_length=2000)]


class LlmUnit(_Strict):
    title: Annotated[str, Field(min_length=1, max_length=300), AfterValidator(_no_nul)]
    summary: Annotated[str, Field(min_length=1, max_length=MAX_SUMMARY_CHARS), AfterValidator(_no_nul)]
    kind: Kind
    merge_into: str | None
    lineage: Annotated[list[str], Field(max_length=20)]
    anchors: Annotated[list[LlmAnchor], Field(max_length=MAX_ANCHORS_PER_UNIT)]


class LlmChunks(_Strict):
    units: Annotated[list[LlmUnit], Field(max_length=MAX_UNITS_OUT)]


# --- Result ---------------------------------------------------------------------------------


class Anchor(_Strict):
    source: Source
    document_id: uuid.UUID | None
    page_no: int | None
    start: int
    end: int
    quote_text: str  # original[start:end], never the string the model returned


class NewUnit(_Strict):
    title: str
    summary: str
    kind: Kind
    section_id: uuid.UUID | None = None
    lineage: list[uuid.UUID]
    single_source: bool
    anchors: list[Anchor]


class AnchorAddition(_Strict):
    """Anchors to add to an existing unit. Nothing else about the unit changes (AC4)."""

    existing_unit_id: uuid.UUID
    anchors: list[Anchor]


class Dropped(_Strict):
    """Something the code refused. Rule name only: no source text."""

    kind: Literal["anchor", "unit"]
    reason: str


class ChunkResult(_Strict):
    new_units: list[NewUnit]
    merges: list[AnchorAddition]
    dropped: list[Dropped]

    @property
    def dropped_anchors(self) -> int:
        return sum(1 for d in self.dropped if d.kind == "anchor")

    @property
    def dropped_units(self) -> int:
        return sum(1 for d in self.dropped if d.kind == "unit")
