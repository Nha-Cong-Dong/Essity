"""ai-service's POST /v1/grade-practice and /v1/draft-answer answers, as core-api reads them (T8.4).
core-api cannot import ai-service, so this is its own strict copy: an answer outside the contract
is not trusted (R03 layer 2). `status` is `ok`, `failed` (the reply broke a rule) or `pending_ai`
(quota or model down)."""

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict

Verdict = Literal["correct", "partial", "incorrect"]
Status = Literal["ok", "failed", "pending_ai"]


class _Reply(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Status
    failure: str | None = None
    provider: str | None = None
    model: str | None = None
    prompt_version: str
    run_id: uuid.UUID
    llm_call_id: uuid.UUID | None = None


class IdeaResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    verdict: Verdict
    anchor: str | None = None


class PracticeGradeReply(_Reply):
    overall: Verdict | None = None
    ideas: list[IdeaResult] = []
    differs_from_card_id: uuid.UUID | None = None


class DraftAnswerReply(_Reply):
    answer: str | None = None
    answer_origin: Literal["ai"] | None = None
    card_ids: list[uuid.UUID] = []
