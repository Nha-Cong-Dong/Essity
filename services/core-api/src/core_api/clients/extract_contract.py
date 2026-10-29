"""ai-service's POST /v1/extract-session answer, as core-api reads it (T4.10 contract, T4.12).
core-api cannot import ai-service (scripts/check_cross_imports.py), so this is its own copy,
strict: an answer outside the contract is not trusted."""

import datetime
import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

Depth = Literal["deep", "skim", "unclear"]
ClarifyReason = Literal["ambiguous_document", "ambiguous_range", "unknown_document", "missing_info"]
Provider = Literal["anthropic", "fake", "none"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class _Common(_Strict):
    provider: Provider
    model: str | None
    prompt_version: str
    run_id: uuid.UUID
    llm_call_id: uuid.UUID | None


class ExtractRange(_Strict):
    document_id: uuid.UUID
    # FILE pages, 1-based; the labels are the printed numbers, for the card.
    start_page: int
    end_page: int
    start_label: str | None
    end_label: str | None
    depth: Depth
    sections: list[str]
    # The learner's printed numbers could not be mapped and were taken as file pages.
    basis_assumed_file: bool


class Proposed(_Common):
    status: Literal["proposed"] = "proposed"
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


class ExtractAnswer(_Strict):
    """Wrapper so the union can be parsed with `model_validate_json`."""

    answer: ExtractResponse
