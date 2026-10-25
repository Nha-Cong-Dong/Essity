"""Grading one answer against the learner's sources (T2.12, US-05).

How a request becomes a prompt:

- The instructions are `prompts/grade/v<N>.md`, sent as the system prompt. Nothing from the
  request goes there, only the nonce.
- Everything from the request (answer, sources, unit titles, question, rubric, reference
  answer) is untrusted text. It goes into the user message, each piece through
  `wrap_untrusted`: HTML-style escaping of `&`, `<`, `>`, inside a block tagged with a nonce
  drawn fresh for each request (ADR-0010; US-05 AC7). Sources go through `render_sources`, the
  only code that reads `quote_text` (VISION §6.3).
- The model never sees ids: units are `U1`, `U2`, ..., anchors `U1.A1`, ... The output schema
  is the same for every request (labels for the largest request allowed), so the provider
  compiles it once; the code checks the labels against the request.
"""

import hashlib
import json
import logging
import re
import secrets
import time
import unicodedata
import uuid
from contextlib import suppress
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, ValidationError
from sqlalchemy import func, update

from ai_service.db.models import PipelineRun
from ai_service.db.session import SessionFactory
from ai_service.llm.client import AuditUnavailableError, LlmClient, LlmUnavailableError
from ai_service.llm.types import LlmRequest
from ai_service.tasks.grade_models import (
    MAX_ANCHORS_PER_UNIT,
    MAX_MISSING_CHARS,
    MAX_MISSING_ITEMS,
    MAX_UNITS,
    GradeRequest,
    GradeResponse,
    GradeUnit,
    UnitVerdict,
    Verdict,
)

_log = logging.getLogger(__name__)

PROMPT_VERSION = "v1"
# services/ai-service/prompts, wherever the process runs from (the image copies it to /app).
_PROMPTS = Path(__file__).resolve().parents[3] / "prompts"
_NONCE_PLACEHOLDER = "{{NONCE}}"

UNIT_LABELS = [f"U{u}" for u in range(1, MAX_UNITS + 1)]
ANCHOR_LABELS = [f"{unit}.A{a}" for unit in UNIT_LABELS for a in range(1, MAX_ANCHORS_PER_UNIT + 1)]

# What the model must answer. `overall` is not in it: the code derives it (R03.4). Lengths and
# counts are not expressible in structured outputs; the R03 checks enforce them.
OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "units": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "unit": {"type": "string", "enum": UNIT_LABELS},
                    "verdict": {"type": "string", "enum": ["correct", "partial", "incorrect"]},
                },
                "required": ["unit", "verdict"],
                "additionalProperties": False,
            },
        },
        "missing": {"type": "array", "items": {"type": "string"}},
        "anchors_used": {"type": "array", "items": {"type": "string", "enum": ANCHOR_LABELS}},
        "understanding": {"anyOf": [{"type": "integer", "enum": [1, 2, 3]}, {"type": "null"}]},
    },
    "required": ["units", "missing", "anchors_used", "understanding"],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class Prompt:
    version: str
    text: str
    sha256: str
    path: str


@lru_cache
def load_prompt(version: str = PROMPT_VERSION) -> Prompt:
    path = _PROMPTS / "grade" / f"{version}.md"
    text = path.read_text("utf-8")
    return Prompt(
        version=version,
        text=text,
        sha256=hashlib.sha256(text.encode()).hexdigest(),
        path=str(path),
    )


def new_nonce() -> str:
    return secrets.token_hex(8)


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def wrap_untrusted(kind: str, text: str, nonce: str, **labels: str) -> str:
    """The one way untrusted text enters a prompt: escaped, inside a nonce-tagged data block.

    `kind` and `labels` are the code's own constants and labels, never request text.
    """
    attributes = "".join(f' {name}="{value}"' for name, value in labels.items())
    return f'<data-{nonce} kind="{kind}"{attributes}>\n{_escape(text)}\n</data-{nonce}>'


@dataclass(frozen=True)
class SourceBlock:
    unit_label: str
    anchor_label: str
    text: str  # as the learner wrote it, for the fake grader only
    block: str  # wrapped and escaped, for the prompt


def render_sources(units: list[GradeUnit], nonce: str) -> list[SourceBlock]:
    """Every anchor of every unit, labelled and wrapped. The only reader of `quote_text`."""
    blocks: list[SourceBlock] = []
    for unit_label, unit in zip(UNIT_LABELS, units, strict=False):
        for a, anchor in enumerate(unit.anchors, start=1):
            anchor_label = f"{unit_label}.A{a}"
            blocks.append(
                SourceBlock(
                    unit_label=unit_label,
                    anchor_label=anchor_label,
                    text=anchor.quote_text,
                    block=wrap_untrusted(
                        "source", anchor.quote_text, nonce, unit=unit_label, anchor=anchor_label
                    ),
                )
            )
    return blocks


@dataclass(frozen=True)
class Labels:
    """Short labels the model sees, and the ids they stand for."""

    units: dict[str, uuid.UUID]
    anchors: dict[str, uuid.UUID]

    @classmethod
    def of(cls, request: GradeRequest) -> "Labels":
        units: dict[str, uuid.UUID] = {}
        anchors: dict[str, uuid.UUID] = {}
        for unit_label, unit in zip(UNIT_LABELS, request.units, strict=False):
            units[unit_label] = unit.unit_id
            for a, anchor in enumerate(unit.anchors, start=1):
                anchors[f"{unit_label}.A{a}"] = anchor.anchor_id
        return cls(units=units, anchors=anchors)


def build_llm_request(
    request: GradeRequest, *, run_id: uuid.UUID, attempt: int, nonce: str | None = None
) -> LlmRequest:
    nonce = nonce or new_nonce()
    prompt = load_prompt()
    sources = render_sources(request.units, nonce)
    question = request.question
    parts = [wrap_untrusted("question", question.text, nonce)]
    if question.rubric is not None:
        parts.append(wrap_untrusted("rubric", question.rubric, nonce))
    parts.append(wrap_untrusted("reference_answer", question.reference_answer, nonce))
    payload_units: list[dict[str, Any]] = []
    for unit_label, unit in zip(UNIT_LABELS, request.units, strict=False):
        parts.append(wrap_untrusted("unit_title", unit.title, nonce, unit=unit_label))
        unit_sources = [source for source in sources if source.unit_label == unit_label]
        parts.extend(source.block for source in unit_sources)
        payload_units.append(
            {
                "label": unit_label,
                "title": unit.title,
                "sources": [{"label": s.anchor_label, "text": s.text} for s in unit_sources],
            }
        )
    parts.append(wrap_untrusted("answer", request.answer, nonce))
    return LlmRequest(
        task="grade",
        user_id=request.user_id,
        subject_id=request.subject_id,
        pipeline_run_id=run_id,
        prompt_version=prompt.version,
        attempt=attempt,
        system=prompt.text.replace(_NONCE_PLACEHOLDER, nonce),
        user="\n\n".join(parts),
        output_schema=OUTPUT_SCHEMA,
        payload={"answer": request.answer, "units": payload_units},
    )


# --- R03: the model's output is checked by code -------------------------------------------


class OutputViolation(Exception):
    """The output broke rule `rule` (schema, units, anchors_used, understanding, missing).

    Carries the rule name only, never the output: it is logged.
    """

    def __init__(self, rule: str) -> None:
        super().__init__(rule)
        self.rule = rule


class _LlmUnit(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    unit: str
    verdict: Verdict


class _LlmGrade(BaseModel):
    # Strict: "2" or true is not an understanding of 2 (rule 7).
    model_config = ConfigDict(extra="forbid", strict=True)
    units: list[_LlmUnit]
    missing: list[str]
    anchors_used: list[str]
    understanding: int | None


@dataclass(frozen=True)
class GradeOutcome:
    overall: Verdict
    understanding: Literal[1, 2, 3] | None
    missing: list[str]
    units: list[UnitVerdict]  # in the request's order
    anchors_used: list[uuid.UUID]


def derive_overall(verdicts: list[Verdict]) -> Verdict:
    """Rule 4: all correct -> correct, all incorrect -> incorrect, anything else -> partial.
    `forgot` never comes from here: it is core's "Không nhớ", without the AI."""
    if all(verdict == "correct" for verdict in verdicts):
        return "correct"
    if all(verdict == "incorrect" for verdict in verdicts):
        return "incorrect"
    return "partial"


def check_output(text: str, labels: Labels) -> GradeOutcome:
    """The rules of R03, in order; the first broken one raises `OutputViolation`."""
    try:
        parsed = _LlmGrade.model_validate_json(text)
    except ValidationError:
        raise OutputViolation("schema") from None  # 7: broken JSON, extra or missing fields

    # 1, 2: exactly the request's units, each once.
    out_units = [unit.unit for unit in parsed.units]
    if len(out_units) != len(set(out_units)) or set(out_units) != set(labels.units):
        raise OutputViolation("units")
    # 3: anchors that were sent for this request's units, each once.
    anchors = parsed.anchors_used
    if len(anchors) != len(set(anchors)) or not set(anchors) <= set(labels.anchors):
        raise OutputViolation("anchors_used")

    verdicts: dict[str, Verdict] = {unit.unit: unit.verdict for unit in parsed.units}
    ordered: list[Verdict] = [verdicts[label] for label in labels.units]
    overall = derive_overall(ordered)

    # 5: understanding 1..3 when right, null when wrong (core's understanding_when_right).
    understanding = parsed.understanding
    if overall == "incorrect":
        if understanding is not None:
            raise OutputViolation("understanding")
    elif understanding not in (1, 2, 3):
        raise OutputViolation("understanding")

    # 6: none when correct; otherwise 1..3 short, non-blank points.
    missing = parsed.missing
    if overall == "correct":
        if missing:
            raise OutputViolation("missing")
    elif not 1 <= len(missing) <= MAX_MISSING_ITEMS or any(
        not point.strip() or len(point) > MAX_MISSING_CHARS for point in missing
    ):
        raise OutputViolation("missing")

    return GradeOutcome(
        overall=overall,
        understanding=understanding,
        missing=missing,
        units=[
            UnitVerdict(unit_id=unit_id, verdict=verdicts[label])
            for label, unit_id in labels.units.items()
        ],
        anchors_used=[labels.anchors[label] for label in anchors],
    )


def missing_points(titles: list[str]) -> list[str]:
    """Rule 6 for answers graded by code: the first three titles, cut to the length limit."""
    return [title[:MAX_MISSING_CHARS] for title in titles[:MAX_MISSING_ITEMS]]


def empty_answer_output(request: GradeRequest, labels: Labels) -> str:
    """What an empty answer gets, as an output, so it passes the same checks (🟠6)."""
    return json.dumps(
        {
            "units": [{"unit": label, "verdict": "incorrect"} for label in labels.units],
            "missing": missing_points([unit.title for unit in request.units]),
            "anchors_used": [],
            "understanding": None,
        }
    )


# --- One grading run ------------------------------------------------------------------------

# The whole request, every call included (B2): core cuts at 10 s.
DEADLINE_SECONDS = 9.0


class GradeInvalidError(Exception):
    """The output broke R03 twice: 502 grade_invalid."""


def grade_answer(
    request: GradeRequest, *, llm: LlmClient, sessions: SessionFactory
) -> GradeResponse:
    """Grade one answer: record the run, ask the model (at most twice), check, answer."""
    deadline = time.monotonic() + DEADLINE_SECONDS
    prompt = load_prompt()
    run_id = _start_run(sessions, request, prompt)
    labels = Labels.of(request)
    try:
        if not request.answer.strip():
            outcome = check_output(empty_answer_output(request, labels), labels)
            response = _response(outcome, run_id, prompt, provider="none", model=None, call=None)
        else:
            response = _ask_model(request, labels, run_id, prompt, llm, deadline)
    except AuditUnavailableError:
        raise
    except GradeInvalidError:
        _finish_run(sessions, run_id, "grade_invalid")
        raise
    except LlmUnavailableError:
        _finish_run(sessions, run_id, "llm_unavailable")
        raise
    except Exception:
        with suppress(AuditUnavailableError):
            _finish_run(sessions, run_id, "internal_error")
        raise
    _finish_run(sessions, run_id, None)
    return response


def _ask_model(
    request: GradeRequest,
    labels: Labels,
    run_id: uuid.UUID,
    prompt: Prompt,
    llm: LlmClient,
    deadline: float,
) -> GradeResponse:
    nonce = new_nonce()
    for attempt in (1, 2):
        llm_request = build_llm_request(request, run_id=run_id, attempt=attempt, nonce=nonce)
        result = llm.call(llm_request, deadline=deadline)
        try:
            outcome = check_output(result.text, labels)
        except OutputViolation as violation:
            _log.warning(
                "grade output refused",
                extra={
                    "outcome": violation.rule,
                    "attempt": attempt,
                    "llm_call_id": str(result.llm_call_id),
                },
            )
            continue
        return _response(
            outcome,
            run_id,
            prompt,
            provider=result.provider,
            model=result.model,
            call=result.llm_call_id,
        )
    raise GradeInvalidError


def _response(
    outcome: GradeOutcome,
    run_id: uuid.UUID,
    prompt: Prompt,
    *,
    provider: str,
    model: str | None,
    call: uuid.UUID | None,
) -> GradeResponse:
    return GradeResponse(
        provider=provider,
        model=model,
        prompt_version=prompt.version,
        run_id=run_id,
        llm_call_id=call,
        overall=outcome.overall,
        understanding=outcome.understanding,
        missing=outcome.missing,
        units=outcome.units,
        anchors_used=outcome.anchors_used,
    )


def _start_run(sessions: SessionFactory, request: GradeRequest, prompt: Prompt) -> uuid.UUID:
    """Committed before any call: no paid call without its run (🟡d)."""
    run = PipelineRun(
        user_id=request.user_id,
        subject_id=request.subject_id,
        attempt_id=request.attempt_id,
        task="grade",
        prompt_version=prompt.version,
        prompt_sha256=prompt.sha256,
    )
    try:
        with sessions() as session:
            session.add(run)
            session.commit()
    except Exception as error:
        _log.exception("pipeline_run not written")
        raise AuditUnavailableError from error
    return run.id


def _finish_run(sessions: SessionFactory, run_id: uuid.UUID, error_code: str | None) -> None:
    try:
        with sessions() as session:
            session.execute(
                update(PipelineRun)
                .where(PipelineRun.id == run_id)
                .values(
                    status="failed" if error_code else "succeeded",
                    error_code=error_code,
                    finished_at=func.now(),
                )
            )
            session.commit()
    except Exception as error:
        _log.exception("pipeline_run not closed")
        raise AuditUnavailableError from error


# --- The fake grader (AI_LLM_PROVIDER=fake: local and test only) --------------------------

_WORD = re.compile(r"\w+")


def _words(text: str) -> set[str]:
    """NFC, casefold, \\w+ words of 2 characters or more."""
    normalized = unicodedata.normalize("NFC", text).casefold()
    return {word for word in _WORD.findall(normalized) if len(word) >= 2}


def _fake_verdict(answer_words: set[str], source_words: set[str]) -> Verdict:
    if not source_words:
        return "incorrect"
    coverage = len(answer_words & source_words) / len(source_words)
    if coverage >= 0.5:
        return "correct"
    if coverage >= 0.2:
        return "partial"
    return "incorrect"


def fake_grade(request: LlmRequest) -> str:
    """A deterministic grade from word coverage, shaped like a model's output (PLAN T2.10).

    A unit is correct when the answer has at least half the words of its sources, partial from
    a fifth. Its output goes through the same R03 checks as a model's.
    """
    payload = request.payload
    answer_words = _words(payload["answer"])
    units: list[dict[str, Any]] = payload["units"]
    verdicts: list[Verdict] = [
        _fake_verdict(answer_words, _words(" ".join(s["text"] for s in unit["sources"])))
        for unit in units
    ]
    overall = derive_overall(verdicts)
    wrong = [unit["title"] for unit, v in zip(units, verdicts, strict=True) if v == "incorrect"]
    partial = [unit["title"] for unit, v in zip(units, verdicts, strict=True) if v == "partial"]
    return json.dumps(
        {
            "units": [
                {"unit": unit["label"], "verdict": verdict}
                for unit, verdict in zip(units, verdicts, strict=True)
            ],
            "missing": missing_points(wrong + partial),
            "anchors_used": [
                source["label"]
                for unit, verdict in zip(units, verdicts, strict=True)
                if verdict != "incorrect"
                for source in unit["sources"]
            ],
            "understanding": {"correct": 3, "partial": 2, "incorrect": None}[overall],
        },
        ensure_ascii=False,
    )
