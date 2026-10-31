"""submission-context.v1 (T7.6, spec v2 §16.3), ai-service's own copy of
`contracts/files/submission-context.v1`.

core-api writes it at `context_key` when the learner submits; ai-service reads it. The learner's
description (untrusted text) travels here, never in the event (ADR-0013). Not shared by import
with core-api (ADR-0003).
"""

import uuid
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, hide_input_in_errors=True)


class Mention(_Closed):
    document_id: uuid.UUID
    section_id: uuid.UUID | None
    # 1-based positions in the document's file; null when the section has none.
    first_page: Annotated[int, Field(ge=1)] | None
    last_page: Annotated[int, Field(ge=1)] | None


class ExistingUnit(_Closed):
    unit_id: uuid.UUID
    title: Annotated[str, Field(min_length=1, max_length=200)]
    summary: Annotated[str, Field(max_length=2000)]


class SubmissionContext(_Closed):
    version: Annotated[int, Field(ge=1, le=1)]
    description: Annotated[str, Field(max_length=2000)] | None
    mentions: Annotated[list[Mention], Field(max_length=20)]
    existing_units: Annotated[list[ExistingUnit], Field(max_length=200)]


def parse_context(raw: str | bytes) -> SubmissionContext:
    """Validate a context file (JSON text). Raises `pydantic.ValidationError`."""
    return SubmissionContext.model_validate_json(raw)
