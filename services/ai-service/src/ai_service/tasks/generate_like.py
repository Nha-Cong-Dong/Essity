"""More practice questions in the style of a sample, with two filters (T9.6a, US-17).

The core is pure: `generate_like(request, ask)` where `ask` sends a `LikePrompt` to the model and
returns its text (T9.6b binds it to `LlmClient`, the quota guard and the `Task` literal; tests
bind it to a fake). Steps, in one pass with no retry (AC6):
  1. one call asks for up to 5 candidates from the studied cards only (the "no bank" path is the
     same call with no sample and a default type name);
  2. code filter (`question_filter`): citing an unstudied card, or being too close to the sample,
     an existing question or an earlier candidate, drops a candidate;
  3. ONE judge call checks J1-J5 on every survivor.
Untrusted text enters prompts only through `wrap_untrusted`; the model sees labels (`S1`, `C1`,
`Q1`), never ids. Model output is untrusted: schema, sizes and labels are checked here. Reasons
are rule names: no source or model text reaches a reason, a log or an exception (ADR-0013).
A quota or availability error becomes the `pending_ai` outcome.
"""

import hashlib
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, ValidationError

from ai_service.llm.client import LlmUnavailableError
from ai_service.llm.quota import QuotaExceededError, QuotaUnavailableError
from ai_service.tasks.grade import new_nonce, wrap_untrusted
from ai_service.tasks.question_filter import (
    REASON_NEAR_DUPLICATE,
    cited_cards_reason,
    is_near_duplicate,
)

_log = logging.getLogger(__name__)

GENERATE_TASK = "generate_like"
JUDGE_TASK = "judge_questions"
PROMPT_VERSION = "v1"
_PROMPTS = Path(__file__).resolve().parents[3] / "prompts"
_NONCE_PLACEHOLDER = "{{NONCE}}"

MAX_CANDIDATES = 5
MAX_SAMPLES = 3
MAX_CARDS = 40
MAX_EXISTING = 200
MAX_TYPE_CHARS = 100
MAX_CARD_CHARS = 1500
MAX_PROMPT_CHARS = 500
MAX_REFERENCE_CHARS = 1500
MAX_RUBRIC_CHARS = 1500
MAX_TOTAL_CHARS = 100_000
MAX_OUTPUT_CHARS = 40_000
MAX_CITED_CARDS = 6
DEFAULT_TYPE_NAME = "Short answer"

REASON_TOO_MANY = "too_many"
REASON_JUDGE_MISSING = "judge_missing"
# J1-J5 reason codes, in checklist order.
JUDGE_REASONS = {
    "j1": "judge_j1_type",
    "j2": "judge_j2_paraphrase",
    "j3": "judge_j3_generic",
    "j4": "judge_j4_unanswerable",
    "j5": "judge_j5_incomplete",
}
FAIL_NO_CARDS = "no_cards"
FAIL_GENERATION_MALFORMED = "generation_malformed"
FAIL_JUDGE_MALFORMED = "judge_malformed"


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


class SampleQuestion(_Strict):
    prompt: Annotated[Filled, Field(max_length=MAX_PROMPT_CHARS)]


class StudiedCard(_Strict):
    card_id: uuid.UUID
    text: Annotated[Filled, Field(max_length=MAX_CARD_CHARS)]


class LikeRequest(_Strict):
    """`cards` holds studied cards only: the caller filters (core-api owns "studied")."""

    type_name: Annotated[Filled, Field(max_length=MAX_TYPE_CHARS)] = DEFAULT_TYPE_NAME
    samples: Annotated[list[SampleQuestion], Field(max_length=MAX_SAMPLES)] = []
    # Prompts of the questions already there (stored or generated): only for the duplicate check.
    existing_prompts: Annotated[list[str], Field(max_length=MAX_EXISTING)] = []
    cards: Annotated[list[StudiedCard], Field(max_length=MAX_CARDS)]
    count: Annotated[int, Field(ge=1, le=MAX_CANDIDATES)] = MAX_CANDIDATES


# --- What the model may say -----------------------------------------------------------------


class LlmCandidate(_Strict):
    prompt: Annotated[Filled, Field(max_length=MAX_PROMPT_CHARS)]
    reference_answer: Annotated[Filled, Field(max_length=MAX_REFERENCE_CHARS)]
    rubric: Annotated[Filled, Field(max_length=MAX_RUBRIC_CHARS)]
    cards: Annotated[list[str], Field(max_length=MAX_CITED_CARDS)]


class LlmCandidates(_Strict):
    candidates: Annotated[list[LlmCandidate], Field(max_length=MAX_CANDIDATES * 4)]


class LlmVerdict(_Strict):
    candidate: str  # "Q1"
    j1: bool
    j2: bool
    j3: bool
    j4: bool
    j5: bool


class LlmVerdicts(_Strict):
    verdicts: Annotated[list[LlmVerdict], Field(max_length=MAX_CANDIDATES * 4)]


GENERATE_SCHEMA: dict[str, Any] = LlmCandidates.model_json_schema()
JUDGE_SCHEMA: dict[str, Any] = LlmVerdicts.model_json_schema()


# --- Result ---------------------------------------------------------------------------------


class KeptCandidate(_Strict):
    prompt: str
    reference_answer: str
    rubric: str
    card_ids: list[uuid.UUID]


class DroppedCandidate(_Strict):
    """Rule name only: no text from the model, the sample or the cards."""

    reason: str


class LikeResult(_Strict):
    """`ok`: at least one kept. `empty`: nothing passed (neutral, no retry); `failure` names a
    malformed model reply or a missing input, else None. `pending_ai`: quota or model down."""

    status: Literal["ok", "empty", "pending_ai"]
    kept: list[KeptCandidate] = []
    dropped: list[DroppedCandidate] = []
    failure: str | None = None


class LikeInputError(Exception):
    """The request cannot be used as it is. Carries the rule name only."""

    def __init__(self, rule: str) -> None:
        super().__init__(rule)
        self.rule = rule


# --- Prompts --------------------------------------------------------------------------------


@dataclass(frozen=True)
class LikePrompt:
    task: Literal["generate_like", "judge_questions"]
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
def load_prompt(task: str, version: str = PROMPT_VERSION) -> Prompt:
    text = (_PROMPTS / task / f"{version}.md").read_text("utf-8")
    return Prompt(version=version, text=text, sha256=hashlib.sha256(text.encode()).hexdigest())


def _check_limits(request: LikeRequest) -> None:
    total = (
        len(request.type_name)
        + sum(len(s.prompt) for s in request.samples)
        + sum(len(c.text) for c in request.cards)
    )
    if total > MAX_TOTAL_CHARS:
        raise LikeInputError("total_chars")
    if len({c.card_id for c in request.cards}) != len(request.cards):
        raise LikeInputError("duplicate_card")


def _nonce_for(texts: list[str]) -> str:
    nonce = new_nonce()
    corpus = "\n".join(texts)
    while nonce in corpus:
        nonce = new_nonce()
    return nonce


def _context_blocks(request: LikeRequest, nonce: str) -> list[str]:
    blocks = [wrap_untrusted("type", request.type_name, nonce)]
    blocks += [
        wrap_untrusted("sample", s.prompt, nonce, label=f"S{n}")
        for n, s in enumerate(request.samples, start=1)
    ]
    blocks += [
        wrap_untrusted("card", c.text, nonce, label=f"C{n}")
        for n, c in enumerate(request.cards, start=1)
    ]
    return blocks


def _texts(request: LikeRequest) -> list[str]:
    return [
        request.type_name,
        *(s.prompt for s in request.samples),
        *(c.text for c in request.cards),
    ]


def build_generate_prompt(request: LikeRequest) -> LikePrompt:
    nonce = _nonce_for(_texts(request))
    blocks = _context_blocks(request, nonce)
    blocks.append(wrap_untrusted("count", str(request.count), nonce))
    system = load_prompt(GENERATE_TASK).text.replace(_NONCE_PLACEHOLDER, nonce)
    return LikePrompt(GENERATE_TASK, system, "\n\n".join(blocks), GENERATE_SCHEMA, nonce)


def build_judge_prompt(request: LikeRequest, candidates: list[LlmCandidate]) -> LikePrompt:
    texts = _texts(request)
    for c in candidates:
        texts += [c.prompt, c.reference_answer, c.rubric]
    nonce = _nonce_for(texts)
    blocks = _context_blocks(request, nonce)
    for n, c in enumerate(candidates, start=1):
        body = f"{c.prompt}\n\nReference answer: {c.reference_answer}\n\nRubric: {c.rubric}"
        blocks.append(wrap_untrusted("candidate", body, nonce, label=f"Q{n}"))
    system = load_prompt(JUDGE_TASK).text.replace(_NONCE_PLACEHOLDER, nonce)
    return LikePrompt(JUDGE_TASK, system, "\n\n".join(blocks), JUDGE_SCHEMA, nonce)


# --- Checks ---------------------------------------------------------------------------------


class _Malformed(Exception):
    pass


def _parse_candidates(text: str) -> list[LlmCandidate]:
    if len(text) > MAX_OUTPUT_CHARS:
        raise _Malformed
    try:
        return LlmCandidates.model_validate_json(text).candidates
    except ValidationError:
        raise _Malformed from None  # never carries the text


def _parse_verdicts(text: str, count: int) -> dict[str, LlmVerdict]:
    if len(text) > MAX_OUTPUT_CHARS:
        raise _Malformed
    try:
        verdicts = LlmVerdicts.model_validate_json(text).verdicts
    except ValidationError:
        raise _Malformed from None
    labels = {f"Q{n}" for n in range(1, count + 1)}
    by_label: dict[str, LlmVerdict] = {}
    for verdict in verdicts:
        if verdict.candidate not in labels or verdict.candidate in by_label:
            raise _Malformed  # an unknown or repeated label: the reply cannot be trusted
        by_label[verdict.candidate] = verdict
    return by_label


def _code_filter(
    request: LikeRequest, candidates: list[LlmCandidate]
) -> tuple[list[tuple[LlmCandidate, list[uuid.UUID]]], list[DroppedCandidate]]:
    studied = {f"C{n}": c.card_id for n, c in enumerate(request.cards, start=1)}
    labels = frozenset(studied)
    references = [s.prompt for s in request.samples] + list(request.existing_prompts)
    passed: list[tuple[LlmCandidate, list[uuid.UUID]]] = []
    dropped: list[DroppedCandidate] = []
    for index, candidate in enumerate(candidates):
        if index >= request.count:
            dropped.append(DroppedCandidate(reason=REASON_TOO_MANY))
            continue
        reason = cited_cards_reason(candidate.cards, labels)
        if reason is None and is_near_duplicate(
            candidate.prompt, [*references, *(p.prompt for p, _ in passed)]
        ):
            reason = REASON_NEAR_DUPLICATE
        if reason is not None:
            dropped.append(DroppedCandidate(reason=reason))
            continue
        ids = list(dict.fromkeys(studied[label] for label in candidate.cards))
        passed.append((candidate, ids))
    return passed, dropped


def _empty(dropped: list[DroppedCandidate], failure: str | None = None) -> LikeResult:
    return LikeResult(status="empty", dropped=dropped, failure=failure)


def generate_like(request: LikeRequest, ask: Callable[[LikePrompt], str]) -> LikeResult:
    """At most two `ask` calls (generate, then judge), never a retry. Model trouble does not
    raise: malformed output gives an empty result with `failure`, quota gives `pending_ai`."""
    _check_limits(request)
    if not request.cards:
        return _empty([], FAIL_NO_CARDS)
    try:
        try:
            candidates = _parse_candidates(ask(build_generate_prompt(request)))
        except _Malformed:
            _log.warning(
                "generated questions refused", extra={"outcome": FAIL_GENERATION_MALFORMED}
            )
            return _empty([], FAIL_GENERATION_MALFORMED)
        survivors, dropped = _code_filter(request, candidates)
        if not survivors:
            return _empty(dropped)
        try:
            verdicts = _parse_verdicts(
                ask(build_judge_prompt(request, [c for c, _ in survivors])), len(survivors)
            )
        except _Malformed:
            _log.warning("judge output refused", extra={"outcome": FAIL_JUDGE_MALFORMED})
            return _empty(dropped, FAIL_JUDGE_MALFORMED)
    except (LlmUnavailableError, QuotaExceededError, QuotaUnavailableError):
        return LikeResult(status="pending_ai")
    kept: list[KeptCandidate] = []
    for n, (candidate, ids) in enumerate(survivors, start=1):
        verdict = verdicts.get(f"Q{n}")
        if verdict is None:
            dropped.append(DroppedCandidate(reason=REASON_JUDGE_MISSING))
            continue
        failed = [code for key, code in JUDGE_REASONS.items() if not getattr(verdict, key)]
        if failed:
            dropped.append(DroppedCandidate(reason=failed[0]))
            continue
        kept.append(
            KeptCandidate(
                prompt=candidate.prompt.strip(),
                reference_answer=candidate.reference_answer.strip(),
                rubric=candidate.rubric.strip(),
                card_ids=ids,
            )
        )
    if not kept:
        return _empty(dropped)
    return LikeResult(status="ok", kept=kept, dropped=dropped)
