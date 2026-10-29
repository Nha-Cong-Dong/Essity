"""Level-1 question generation for knowledge units (T4.16a, US-04b "nhan biet").

The core is pure: `generate_questions(request, ask)` where `ask` sends a `QuestionPrompt` to the
model and returns its text. T4.16b binds `ask` to `LlmClient` and the quota guard; tests bind it
to a fake.

- Untrusted text (unit titles, summaries, anchored quotes) enters the prompt only through
  `wrap_untrusted`. The model sees labels (`U1`, `U1.A1`), never ids.
- The model's output is untrusted too: the code checks the schema, every length, NUL, that the
  unit label exists in the input, and that every unit got at least one question. Rules refuse by
  name only: no source or model text reaches an exception, a log or `DroppedQuestion` (ADR-0013).
- A unit left without a question fails the attempt (retry); after `ATTEMPTS` the call raises.
"""

import hashlib
import logging
import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from ai_service.tasks.grade import new_nonce, wrap_untrusted
from ai_service.tasks.question_models import (
    MAX_OUTPUT_CHARS,
    MAX_QUESTIONS_PER_UNIT,
    MAX_TOTAL_CHARS,
    DroppedQuestion,
    GeneratedQuestion,
    LlmQuestions,
    QuestionRequest,
    QuestionResult,
)

_log = logging.getLogger(__name__)

TASK = "generate_questions"
PROMPT_VERSION = "v1"
_PROMPTS = Path(__file__).resolve().parents[3] / "prompts"
_NONCE_PLACEHOLDER = "{{NONCE}}"
ATTEMPTS = 2

OUTPUT_SCHEMA: dict[str, Any] = LlmQuestions.model_json_schema()


class QuestionInputError(Exception):
    """The request cannot be used as it is. Carries the rule name only."""

    def __init__(self, rule: str) -> None:
        super().__init__(rule)
        self.rule = rule


class QuestionInputTooLarge(QuestionInputError):
    """Over a size limit: refused, never cut silently (T4.16b splits into batches)."""


class QuestionsInvalidError(Exception):
    """The model broke the output rules on every attempt."""


class OutputViolation(Exception):
    """The output broke rule `rule`. Carries the rule name only: it is logged."""

    def __init__(self, rule: str) -> None:
        super().__init__(rule)
        self.rule = rule


@dataclass(frozen=True)
class QuestionPrompt:
    system: str
    user: str
    output_schema: dict[str, Any]
    nonce: str


@dataclass(frozen=True)
class Prompt:
    version: str
    text: str
    sha256: str


@lru_cache
def load_prompt(version: str = PROMPT_VERSION) -> Prompt:
    text = (_PROMPTS / TASK / f"{version}.md").read_text("utf-8")
    return Prompt(version=version, text=text, sha256=hashlib.sha256(text.encode()).hexdigest())


def _labels(request: QuestionRequest) -> dict[str, uuid.UUID]:
    labels: dict[str, uuid.UUID] = {}
    for n, unit in enumerate(request.units, start=1):
        if unit.unit_id in labels.values():
            raise QuestionInputError("duplicate_unit")
        labels[f"U{n}"] = unit.unit_id
    return labels


def _check_limits(request: QuestionRequest) -> None:
    total = sum(len(u.title) + len(u.summary) + sum(map(len, u.quotes)) for u in request.units)
    if total > MAX_TOTAL_CHARS:
        raise QuestionInputTooLarge("total_chars")


def _corpus(request: QuestionRequest) -> str:
    return "\n".join(t for u in request.units for t in (u.title, u.summary, *u.quotes))


def build_prompt(request: QuestionRequest) -> QuestionPrompt:
    corpus = _corpus(request)
    nonce = new_nonce()
    while nonce in corpus:
        nonce = new_nonce()
    blocks: list[str] = []
    for n, unit in enumerate(request.units, start=1):
        label = f"U{n}"
        blocks.append(wrap_untrusted("unit", f"{unit.title}\n{unit.summary}", nonce, label=label))
        for a, quote in enumerate(unit.quotes, start=1):
            blocks.append(wrap_untrusted("source", quote, nonce, label=f"{label}.A{a}"))
    system = load_prompt().text.replace(_NONCE_PLACEHOLDER, nonce)
    return QuestionPrompt(system, "\n\n".join(blocks), OUTPUT_SCHEMA, nonce)


def _fold(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


def check_questions(text: str, labels: dict[str, uuid.UUID]) -> QuestionResult:
    """Parse and verify the model's text. The first broken rule raises `OutputViolation`."""
    if len(text) > MAX_OUTPUT_CHARS:
        raise OutputViolation("too_long")
    try:
        parsed = LlmQuestions.model_validate_json(text)
    except ValidationError:
        raise OutputViolation("schema") from None  # never carries the text
    questions: list[GeneratedQuestion] = []
    dropped: list[DroppedQuestion] = []
    seen: dict[uuid.UUID, set[str]] = {}
    for item in parsed.questions:
        unit_id = labels.get(item.unit)
        if unit_id is None:
            dropped.append(DroppedQuestion(reason="unknown_unit"))
            continue
        prompts = seen.setdefault(unit_id, set())
        folded = _fold(item.prompt)
        if folded in prompts:
            dropped.append(DroppedQuestion(reason="duplicate"))
            continue
        if len(prompts) >= MAX_QUESTIONS_PER_UNIT:
            dropped.append(DroppedQuestion(reason="too_many"))
            continue
        prompts.add(folded)
        questions.append(
            GeneratedQuestion(
                unit_id=unit_id,
                prompt=item.prompt.strip(),
                reference_answer=item.reference_answer.strip(),
                rubric=item.rubric.strip(),
            )
        )
    if any(unit_id not in seen for unit_id in labels.values()):
        raise OutputViolation("unit_uncovered")
    return QuestionResult(questions=questions, dropped=dropped)


def generate_questions(
    request: QuestionRequest, ask: Callable[[QuestionPrompt], str]
) -> QuestionResult:
    """At least one level-1 question per unit, each checked by code."""
    _check_limits(request)
    labels = _labels(request)
    if not labels:
        return QuestionResult(questions=[], dropped=[])
    prompt = build_prompt(request)
    for attempt in range(1, ATTEMPTS + 1):
        try:
            return check_questions(ask(prompt), labels)
        except OutputViolation as violation:
            _log.warning(
                "question output refused", extra={"outcome": violation.rule, "attempt": attempt}
            )
    raise QuestionsInvalidError
