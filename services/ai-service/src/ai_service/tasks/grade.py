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
import secrets
import uuid
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from ai_service.llm.types import LlmRequest
from ai_service.tasks.grade_models import (
    MAX_ANCHORS_PER_UNIT,
    MAX_UNITS,
    GradeRequest,
    GradeUnit,
)

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
