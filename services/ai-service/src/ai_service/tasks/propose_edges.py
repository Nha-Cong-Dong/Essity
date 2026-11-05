"""POST /v1/propose-edges (T9.9, US-19 AC2): relations between one saved card and some candidates.

core-api sends the saved card and up to `MAX_CANDIDATES` other cards of the same subject (title,
summary, anchored quotes: ai-service holds none of it). One model call per request, so the calls
of a Save do not depend on how many cards the subject has. The model sees labels (`S`, `C1`), never
ids. Its answer is untrusted: the code checks the schema, the kind, the labels, and that every
quote occurs in the anchors of the card it names (whitespace folded); an edge left without a valid
quote is dropped, never kept (no evidence, no edge). core-api checks again before it stores.
Rules are named in logs; no card text or model text is logged (ADR-0013).
"""

import hashlib
import json
import logging
import re
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Final, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, ValidationError

from ai_service.db.session import SessionFactory
from ai_service.llm.client import LlmClient, LlmUnavailableError
from ai_service.llm.quota import QuotaExceededError, QuotaUnavailableError
from ai_service.llm.types import LlmRequest, LlmResult
from ai_service.tasks.grade import new_nonce, wrap_untrusted
from ai_service.tasks.practice_run import (
    DEADLINE_SECONDS,
    RunInfo,
    _finish_run,  # pyright: ignore[reportPrivateUsage]
    _start_run,  # pyright: ignore[reportPrivateUsage]
)
from ai_service.tasks.question_models import QuestionUnit

_log = logging.getLogger(__name__)

TASK: Final = "propose_edges"
PROMPT_VERSION = "v1"
_PROMPTS = Path(__file__).resolve().parents[3] / "prompts"
_NONCE_PLACEHOLDER = "{{NONCE}}"
MAX_CANDIDATES = 10
MAX_EDGES = 5
MAX_OUTPUT_CHARS = 20_000
MAX_EVIDENCE_PER_EDGE = 3
KINDS = ("prerequisite", "part_of", "example_of", "contrast", "applies_to")
Kind = Literal["prerequisite", "part_of", "example_of", "contrast", "applies_to"]


def _no_nul(text: str) -> str:
    if "\x00" in text:
        raise ValueError("NUL")
    return text


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


class ProposeEdgesBody(_Strict):
    user_id: uuid.UUID
    subject_id: uuid.UUID
    source: QuestionUnit
    candidates: Annotated[list[QuestionUnit], Field(min_length=1, max_length=MAX_CANDIDATES)]


class EdgeEvidence(_Strict):
    unit_id: uuid.UUID
    quote: str


class ProposedEdge(_Strict):
    kind: Kind
    source_id: uuid.UUID  # `from`: the card that needs, is part of, ...
    target_id: uuid.UUID
    evidence: list[EdgeEvidence]


class ProposeEdgesResponse(RunInfo):
    status: Literal["ok", "failed", "pending_ai"]
    failure: str | None = None
    edges: list[ProposedEdge] = []
    dropped: int = 0


# What the model may say (labels, not ids).
class LlmQuote(_Strict):
    card: str
    quote: Annotated[str, Field(max_length=2000), AfterValidator(_no_nul)]


class LlmEdge(BaseModel):
    model_config = ConfigDict(
        extra="forbid", frozen=True, hide_input_in_errors=True, populate_by_name=True
    )

    kind: str
    from_: Annotated[str, Field(alias="from")]
    to: str
    evidence: Annotated[list[LlmQuote], Field(max_length=MAX_EVIDENCE_PER_EDGE)]


class LlmEdges(_Strict):
    edges: Annotated[list[LlmEdge], Field(max_length=MAX_EDGES * 2)]


OUTPUT_SCHEMA: dict[str, Any] = LlmEdges.model_json_schema(by_alias=True)


@dataclass(frozen=True)
class Prompt:
    version: str
    text: str
    sha256: str


def load_prompt(version: str = PROMPT_VERSION) -> Prompt:
    text = (_PROMPTS / TASK / f"{version}.md").read_text("utf-8")
    return Prompt(version=version, text=text, sha256=hashlib.sha256(text.encode()).hexdigest())


@dataclass(frozen=True)
class BuiltPrompt:
    system: str
    user: str
    nonce: str
    labels: dict[str, QuestionUnit]


class OutputViolation(Exception):
    def __init__(self, rule: str) -> None:
        super().__init__(rule)
        self.rule = rule


def _fold(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def build_prompt(body: ProposeEdgesBody) -> BuiltPrompt:
    labels: dict[str, QuestionUnit] = {"S": body.source}
    labels.update({f"C{n}": c for n, c in enumerate(body.candidates, start=1)})
    corpus = "\n".join(t for u in labels.values() for t in (u.title, u.summary, *u.quotes))
    nonce = new_nonce()
    while nonce in corpus:
        nonce = new_nonce()
    blocks: list[str] = []
    for label, unit in labels.items():
        blocks.append(wrap_untrusted("card", f"{unit.title}\n{unit.summary}", nonce, label=label))
        for a, quote in enumerate(unit.quotes, start=1):
            blocks.append(wrap_untrusted("source", quote, nonce, label=f"{label}.A{a}"))
    system = load_prompt().text.replace(_NONCE_PLACEHOLDER, nonce)
    return BuiltPrompt(system, "\n\n".join(blocks), nonce, labels)


_SOURCE_LABEL = re.compile(r"^(S|C[1-9][0-9]*)\.A([1-9][0-9]*)$")


def _cited(card: str, labels: dict[str, QuestionUnit]) -> tuple[str, list[str]]:
    """The card a quote names, and the anchors it may come from. The model may name the source
    block (`C1.A2`, as the prompt labels it) instead of the card (`C1`): then that one anchor."""
    match = _SOURCE_LABEL.match(card)
    if match is None:
        owner = labels.get(card)
        return card, list(owner.quotes) if owner else []
    label, n = match.group(1), int(match.group(2))
    owner = labels.get(label)
    if owner is None or n > len(owner.quotes):
        return label, []
    return label, [owner.quotes[n - 1]]


def check_edges(text: str, labels: dict[str, QuestionUnit]) -> tuple[list[ProposedEdge], int]:
    """Parse and verify the model's text: the edges that stand, and how many were dropped.
    A broken schema raises `OutputViolation`; a bad edge is dropped, not fatal."""
    if len(text) > MAX_OUTPUT_CHARS:
        raise OutputViolation("too_long")
    try:
        parsed = LlmEdges.model_validate_json(text)
    except ValidationError:
        raise OutputViolation("schema") from None
    edges: list[ProposedEdge] = []
    dropped = 0
    seen: set[tuple[str, str, str]] = set()
    for item in parsed.edges:
        source, target = labels.get(item.from_), labels.get(item.to)
        key = (item.kind, item.from_, item.to)
        if (
            item.kind not in KINDS
            or source is None
            or target is None
            or item.from_ == item.to
            or "S" not in (item.from_, item.to)
            or key in seen
            or len(edges) >= MAX_EDGES
        ):
            dropped += 1
            continue
        evidence: list[EdgeEvidence] = []
        for q in item.evidence:
            card, anchors = _cited(q.card, labels)
            owner = labels.get(card)
            if card not in (item.from_, item.to) or owner is None:
                continue
            quote = _fold(q.quote)
            if quote and any(quote in _fold(a) for a in anchors):
                evidence.append(EdgeEvidence(unit_id=owner.unit_id, quote=quote))
        if not evidence or len(evidence) != len(item.evidence):
            dropped += 1  # no evidence, or a quote that is not in the anchors: no edge
            continue
        seen.add(key)
        edges.append(
            ProposedEdge(
                kind=item.kind,  # pyright: ignore[reportArgumentType]
                source_id=source.unit_id,
                target_id=target.unit_id,
                evidence=evidence,
            )
        )
    return edges, dropped


def run_propose_edges(
    body: ProposeEdgesBody, *, llm: LlmClient, sessions: SessionFactory
) -> ProposeEdgesResponse:
    prompt = load_prompt()
    run_id = _start_run(
        sessions, TASK, body.user_id, body.subject_id, prompt.version, prompt.sha256
    )
    built = build_prompt(body)
    last: list[LlmResult] = []
    deadline = time.monotonic() + DEADLINE_SECONDS
    request = LlmRequest(
        task=TASK,
        user_id=body.user_id,
        subject_id=body.subject_id,
        pipeline_run_id=run_id,
        prompt_version=prompt.version,
        attempt=1,
        system=built.system,
        user=built.user,
        output_schema=OUTPUT_SCHEMA,
        payload={"candidate_quote": next(iter(body.candidates[0].quotes), "")},
    )
    status: Literal["ok", "failed", "pending_ai"] = "ok"
    failure: str | None = None
    edges: list[ProposedEdge] = []
    dropped = 0
    try:
        last.append(llm.call(request, deadline=deadline))
        edges, dropped = check_edges(last[-1].text, built.labels)
    except (LlmUnavailableError, QuotaExceededError, QuotaUnavailableError):
        status = "pending_ai"
    except OutputViolation as violation:
        status, failure = "failed", violation.rule
        _log.warning("edge output refused", extra={"outcome": violation.rule})
    _finish_run(sessions, run_id, "quota_or_unavailable" if status == "pending_ai" else failure)
    info = last[-1] if last else None
    return ProposeEdgesResponse(
        status=status,
        failure=failure,
        edges=edges,
        dropped=dropped,
        prompt_version=prompt.version,
        run_id=run_id,
        provider=info.provider if info else None,
        model=info.model if info else None,
        llm_call_id=info.llm_call_id if info else None,
    )


def fake_propose_edges(request: LlmRequest) -> str:
    """Local and test only: the saved card needs the first candidate, quoting the candidate's
    first anchor (read from `payload`). No candidate quote: no evidence, so no edge."""
    quote = str(request.payload.get("candidate_quote", ""))
    if not quote:
        return json.dumps({"edges": []})
    edge = {
        "kind": "prerequisite",
        "from": "S",
        "to": "C1",
        "evidence": [{"card": "C1", "quote": quote}],
    }
    return json.dumps({"edges": [edge]})
