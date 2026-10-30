"""Grade one practice answer by rubric, idea by idea (T8.4a, US-05 AC9, AC11, AC12, AC14).

The core is pure: `grade_practice(request, ask)` where `ask` sends a `PracticePrompt` to the model
and returns its text (T8.4 binds it to `LlmClient`, the quota guard and the `Task` literal; tests
bind it to a fake). One call, no retry. The prompt holds the question, the rubric ideas, the short
reference answer and the learner's answer: no document text, no anchors, no ids (AC11).
Untrusted text enters only through `wrap_untrusted`; the learner's answer is data, never an
instruction (ADR-0010). The model says `yes | partial | no` per idea; the overall result comes
from `derive_overall` in code. The bank's answer is the standard: `differs_from_card_id` is
passed through to the result for the "differs from card X" line and never reaches the prompt
(AC12). Results and logs hold rule names only: no answer or model text reaches an exception
or a log. A quota or availability error becomes the `pending_ai` outcome (AC14).
"""

import hashlib
import logging
import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, ValidationError

from ai_service.llm.client import LlmUnavailableError
from ai_service.llm.quota import QuotaExceededError, QuotaUnavailableError
from ai_service.tasks.grade import derive_overall, new_nonce, wrap_untrusted
from ai_service.tasks.grade_models import Verdict

_log = logging.getLogger(__name__)

TASK = "grade_practice"
PROMPT_VERSION = "v1"
TEMPERATURE = 0.0
_PROMPTS = Path(__file__).resolve().parents[3] / "prompts"
_NONCE_PLACEHOLDER = "{{NONCE}}"

MAX_IDEAS = 8
MAX_QUESTION_CHARS = 1000
MAX_IDEA_CHARS = 400
MAX_REFERENCE_CHARS = 1500
MAX_ANSWER_CHARS = 8000
MAX_ANCHOR_CHARS = 200
MAX_OUTPUT_CHARS = 10_000

FAIL_MALFORMED = "grade_malformed"
FAIL_ANCHOR = "anchor_not_in_answer"

_VERDICTS: dict[str, Verdict] = {"yes": "correct", "partial": "partial", "no": "incorrect"}


def _no_nul(text: str) -> str:
    if "\x00" in text:
        raise ValueError("NUL")
    return text


def _not_blank(text: str) -> str:
    if not text.strip():
        raise ValueError("blank")
    return text


Filled = Annotated[str, AfterValidator(_no_nul), AfterValidator(_not_blank)]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


# --- Request --------------------------------------------------------------------------------


class PracticeGradeRequest(_Strict):
    question: Annotated[Filled, Field(max_length=MAX_QUESTION_CHARS)]
    rubric: Annotated[
        list[Annotated[Filled, Field(max_length=MAX_IDEA_CHARS)]],
        Field(min_length=1, max_length=MAX_IDEAS),
    ]
    reference_answer: Annotated[Filled, Field(max_length=MAX_REFERENCE_CHARS)]
    answer: Annotated[Filled, Field(max_length=MAX_ANSWER_CHARS)]
    # The card whose standard answer differs from the bank's (AC12): for the result only.
    differs_from_card_id: uuid.UUID | None = None


# --- What the model may say -----------------------------------------------------------------


class LlmIdea(_Strict):
    idea: str  # "R1"
    verdict: Literal["yes", "partial", "no"]
    anchor: Annotated[str, Field(max_length=MAX_ANCHOR_CHARS)] | None


class LlmGrade(_Strict):
    ideas: Annotated[list[LlmIdea], Field(max_length=MAX_IDEAS)]


OUTPUT_SCHEMA: dict[str, Any] = LlmGrade.model_json_schema()


# --- Result ---------------------------------------------------------------------------------


class IdeaResult(_Strict):
    verdict: Verdict
    anchor: str | None


class PracticeGradeResult(_Strict):
    """`ok`: graded. `failed`: the reply broke the rules (`failure` names the rule, no text).
    `pending_ai`: quota or model down; the answer is kept and the grading queued (AC14)."""

    status: Literal["ok", "failed", "pending_ai"]
    overall: Verdict | None = None
    ideas: list[IdeaResult] = []
    differs_from_card_id: uuid.UUID | None = None
    failure: str | None = None


# --- Prompt ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class PracticePrompt:
    task: Literal["grade_practice"]
    system: str
    user: str
    output_schema: dict[str, Any]
    nonce: str
    temperature: float = TEMPERATURE


@dataclass(frozen=True)
class Prompt:
    version: str
    text: str
    sha256: str


@lru_cache
def load_prompt(version: str = PROMPT_VERSION) -> Prompt:
    text = (_PROMPTS / TASK / f"{version}.md").read_text("utf-8")
    return Prompt(version=version, text=text, sha256=hashlib.sha256(text.encode()).hexdigest())


def _nonce_for(texts: list[str]) -> str:
    nonce = new_nonce()
    corpus = "\n".join(texts)
    while nonce in corpus:
        nonce = new_nonce()
    return nonce


def build_prompt(request: PracticeGradeRequest) -> PracticePrompt:
    nonce = _nonce_for(
        [request.question, *request.rubric, request.reference_answer, request.answer]
    )
    blocks = [wrap_untrusted("question", request.question, nonce)]
    blocks += [
        wrap_untrusted("idea", idea, nonce, label=f"R{n}")
        for n, idea in enumerate(request.rubric, start=1)
    ]
    blocks.append(wrap_untrusted("reference", request.reference_answer, nonce))
    blocks.append(wrap_untrusted("answer", request.answer, nonce))
    system = load_prompt().text.replace(_NONCE_PLACEHOLDER, nonce)
    return PracticePrompt(TASK, system, "\n\n".join(blocks), OUTPUT_SCHEMA, nonce)


# --- Checks ---------------------------------------------------------------------------------


class _Malformed(Exception):
    def __init__(self, rule: str) -> None:
        super().__init__(rule)
        self.rule = rule


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


def check_output(text: str, request: PracticeGradeRequest) -> list[IdeaResult]:
    """Every rubric idea exactly once; an anchor is a quote of the learner's answer."""
    if len(text) > MAX_OUTPUT_CHARS:
        raise _Malformed(FAIL_MALFORMED)
    try:
        parsed = LlmGrade.model_validate_json(text)
    except ValidationError:
        raise _Malformed(FAIL_MALFORMED) from None  # never carries the text
    labels = [f"R{n}" for n in range(1, len(request.rubric) + 1)]
    by_label = {i.idea: i for i in parsed.ideas}
    if len(by_label) != len(parsed.ideas) or set(by_label) != set(labels):
        raise _Malformed(FAIL_MALFORMED)
    answer = _norm(request.answer)
    results: list[IdeaResult] = []
    for label in labels:
        idea = by_label[label]
        verdict = _VERDICTS[idea.verdict]
        anchor = idea.anchor.strip() if idea.anchor and idea.anchor.strip() else None
        if verdict == "incorrect":
            anchor = None
        elif anchor is not None and _norm(anchor) not in answer:
            raise _Malformed(FAIL_ANCHOR)
        results.append(IdeaResult(verdict=verdict, anchor=anchor))
    return results


def grade_practice(
    request: PracticeGradeRequest, ask: Callable[[PracticePrompt], str]
) -> PracticeGradeResult:
    """One `ask` call. Model trouble does not raise: a broken reply gives `failed` with the rule
    name, quota or availability gives `pending_ai`."""
    try:
        text = ask(build_prompt(request))
    except (LlmUnavailableError, QuotaExceededError, QuotaUnavailableError):
        return PracticeGradeResult(status="pending_ai")
    try:
        ideas = check_output(text, request)
    except _Malformed as error:
        _log.warning("practice grade refused", extra={"outcome": error.rule})
        return PracticeGradeResult(status="failed", failure=error.rule)
    return PracticeGradeResult(
        status="ok",
        overall=derive_overall([i.verdict for i in ideas]),
        ideas=ideas,
        differs_from_card_id=request.differs_from_card_id,
    )
