"""ai-service's POST /v1/generate-like answer, as core-api reads it (T9.6b, US-17). core-api cannot
import ai-service, so this is its own strict copy: an answer outside the contract is not trusted
(R03 layer 2). `status`: `ok` (at least one kept), `empty` (nothing passed, or `failure` names a
reply that broke a rule), `pending_ai` (quota or model down). `dropped` holds rule names only."""

import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

# ai-service's limits (generate_like.py): a longer text is not a valid candidate.
MAX_PROMPT_CHARS = 500
MAX_REFERENCE_CHARS = 1500
MAX_RUBRIC_CHARS = 1500


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class KeptCandidate(_Strict):
    prompt: Annotated[str, Field(min_length=1, max_length=MAX_PROMPT_CHARS)]
    reference_answer: Annotated[str, Field(min_length=1, max_length=MAX_REFERENCE_CHARS)]
    rubric: Annotated[str, Field(min_length=1, max_length=MAX_RUBRIC_CHARS)]
    card_ids: Annotated[list[uuid.UUID], Field(max_length=6)]


class DroppedCandidate(_Strict):
    reason: str


class LikeReply(_Strict):
    status: Literal["ok", "empty", "pending_ai"]
    kept: list[KeptCandidate] = []
    dropped: list[DroppedCandidate] = []
    failure: str | None = None
    provider: str | None = None
    model: str | None = None
    prompt_version: str
    run_id: uuid.UUID
    llm_call_id: uuid.UUID | None = None
