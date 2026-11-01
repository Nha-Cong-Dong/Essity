"""ai-service's POST /v1/review-question answer, as core-api reads it (T7.9). core-api cannot
import ai-service, so this is its own strict copy: an answer outside the contract is not trusted
(R03 layer 2). `status` is `ok`, `failed` (the reply broke a rule) or `pending_ai` (quota or
model down: the card waits for a question, no error)."""

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict


class ReviewQuestionReply(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["ok", "failed", "pending_ai"]
    failure: str | None = None
    provider: str | None = None
    model: str | None = None
    prompt_version: str
    run_id: uuid.UUID
    llm_call_id: uuid.UUID | None = None
    prompt: str | None = None
    reference_answer: str | None = None
    rubric: str | None = None
