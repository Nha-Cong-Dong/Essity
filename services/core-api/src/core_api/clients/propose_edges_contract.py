"""ai-service's POST /v1/propose-edges answer, as core-api reads it (T9.9). core-api cannot import
ai-service, so this is its own strict copy. The evidence is only a claim: core-api checks every
quote against the anchors it holds before it stores an edge."""

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class EdgeEvidenceReply(_Strict):
    unit_id: uuid.UUID
    quote: str


class ProposedEdgeReply(_Strict):
    kind: str
    source_id: uuid.UUID
    target_id: uuid.UUID
    evidence: list[EdgeEvidenceReply]


class ProposeEdgesReply(_Strict):
    status: Literal["ok", "failed", "pending_ai"]
    failure: str | None = None
    provider: str | None = None
    model: str | None = None
    prompt_version: str
    run_id: uuid.UUID
    llm_call_id: uuid.UUID | None = None
    edges: list[ProposedEdgeReply] = []
    dropped: int = 0
