"""Draft a reference answer for a bank question that has none (T8.4a, US-05 AC13).

Pure core like `grade_practice`: `draft_answer(request, ask)`. The prompt holds the question and,
when there are any, the learner's studied cards (labels `C1`, ...); the model never sees ids.
The result is always labelled `answer_origin = "ai"`, so the screen shows "đáp án do AI soạn";
the learner's own edit later becomes the standard (`user`) in core-api. Cited labels must be
in the input. Rule names only reach results and logs. Quota or availability gives `pending_ai`.
"""

import hashlib
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ai_service.llm.client import LlmUnavailableError
from ai_service.llm.quota import QuotaExceededError, QuotaUnavailableError
from ai_service.tasks.generate_like import MAX_CARD_CHARS, MAX_CARDS, Filled
from ai_service.tasks.grade import new_nonce, wrap_untrusted
from ai_service.tasks.grade_practice import MAX_QUESTION_CHARS

_log = logging.getLogger(__name__)

TASK = "draft_answer"
PROMPT_VERSION = "v1"
TEMPERATURE = 0.0
_PROMPTS = Path(__file__).resolve().parents[3] / "prompts"
_NONCE_PLACEHOLDER = "{{NONCE}}"

MAX_ANSWER_CHARS = 1500
MAX_CITED = 6
MAX_OUTPUT_CHARS = 5000
FAIL_MALFORMED = "draft_malformed"
FAIL_CARD_LABEL = "unknown_card"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


class DraftCard(_Strict):
    card_id: uuid.UUID
    text: Annotated[Filled, Field(max_length=MAX_CARD_CHARS)]


class DraftRequest(_Strict):
    question: Annotated[Filled, Field(max_length=MAX_QUESTION_CHARS)]
    cards: Annotated[list[DraftCard], Field(max_length=MAX_CARDS)] = []


class LlmDraft(_Strict):
    answer: Annotated[Filled, Field(max_length=MAX_ANSWER_CHARS)]
    cards: Annotated[list[str], Field(max_length=MAX_CITED)]


OUTPUT_SCHEMA: dict[str, Any] = LlmDraft.model_json_schema()


class DraftResult(_Strict):
    status: Literal["ok", "failed", "pending_ai"]
    answer: str | None = None
    answer_origin: Literal["ai"] | None = None
    card_ids: list[uuid.UUID] = []
    failure: str | None = None


@dataclass(frozen=True)
class DraftPrompt:
    task: Literal["draft_answer"]
    system: str
    user: str
    output_schema: dict[str, Any]
    nonce: str
    temperature: float = TEMPERATURE


@lru_cache
def _load_prompt(version: str = PROMPT_VERSION) -> str:
    return (_PROMPTS / TASK / f"{version}.md").read_text("utf-8")


def prompt_sha256(version: str = PROMPT_VERSION) -> str:
    return hashlib.sha256(_load_prompt(version).encode()).hexdigest()


def build_prompt(request: DraftRequest) -> DraftPrompt:
    nonce = new_nonce()
    corpus = "\n".join([request.question, *(c.text for c in request.cards)])
    while nonce in corpus:
        nonce = new_nonce()
    blocks = [wrap_untrusted("question", request.question, nonce)]
    blocks += [
        wrap_untrusted("card", c.text, nonce, label=f"C{n}")
        for n, c in enumerate(request.cards, start=1)
    ]
    system = _load_prompt().replace(_NONCE_PLACEHOLDER, nonce)
    return DraftPrompt(TASK, system, "\n\n".join(blocks), OUTPUT_SCHEMA, nonce)


def draft_answer(request: DraftRequest, ask: Callable[[DraftPrompt], str]) -> DraftResult:
    try:
        text = ask(build_prompt(request))
    except (LlmUnavailableError, QuotaExceededError, QuotaUnavailableError):
        return DraftResult(status="pending_ai")
    if len(text) > MAX_OUTPUT_CHARS:
        return _failed(FAIL_MALFORMED)
    try:
        draft = LlmDraft.model_validate_json(text)
    except ValidationError:
        return _failed(FAIL_MALFORMED)
    studied = {f"C{n}": c.card_id for n, c in enumerate(request.cards, start=1)}
    if any(label not in studied for label in draft.cards):
        return _failed(FAIL_CARD_LABEL)
    ids = list(dict.fromkeys(studied[label] for label in draft.cards))
    return DraftResult(status="ok", answer=draft.answer.strip(), answer_origin="ai", card_ids=ids)


def _failed(rule: str) -> DraftResult:
    _log.warning("draft answer refused", extra={"outcome": rule})
    return DraftResult(status="failed", failure=rule)
