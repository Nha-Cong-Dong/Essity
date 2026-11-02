"""ai-service's POST /v1/parse-question-bank answer, as core-api reads it (T8.1b, US-14). core-api
cannot import ai-service, so this is its own strict copy: an answer outside the contract is not
trusted (R03 layer 2). `status`: `ok`, `partial` (something was dropped or a call failed; what
is here was checked), `pending_ai` (quota or model down: no question is returned). `reasons`
holds rule names only."""

import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

# ai-service's limits (question_bank.py): a longer text is not a valid question.
MAX_QUESTIONS = 500
MAX_TEXT_CHARS = 4000
MAX_TYPE_NAME_CHARS = 80
MAX_SECTIONS_PER_QUESTION = 5


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class BankQuestion(_Strict):
    ord: Annotated[int, Field(ge=1, le=MAX_QUESTIONS)]
    prompt: Annotated[str, Field(min_length=1, max_length=MAX_TEXT_CHARS)]
    answer_text: Annotated[str, Field(max_length=MAX_TEXT_CHARS)] | None = None
    source_page: Annotated[int, Field(ge=1)]
    type_name: Annotated[str, Field(min_length=1, max_length=MAX_TYPE_NAME_CHARS)] | None = None
    section_ids: Annotated[list[str], Field(max_length=MAX_SECTIONS_PER_QUESTION)] = []


class BankReply(_Strict):
    status: Literal["ok", "partial", "pending_ai"]
    questions: Annotated[list[BankQuestion], Field(max_length=MAX_QUESTIONS)] = []
    unmapped: list[int] = []
    reasons: list[str] = []
    provider: str | None = None
    model: str | None = None
    prompt_version: str
    run_id: uuid.UUID
    llm_call_id: uuid.UUID | None = None
