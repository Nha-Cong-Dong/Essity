"""Draft knowledge units from a study session's declared scope (T7.7a, v2 US-02b).

The core is pure: `draft_units(request, ask)` where `ask` sends a `ChunkPrompt` to the model and
returns its text. Binding `ask` to `LlmClient` and the quota guard, reading the scope from the
database and writing the drafts is T7.7's work; nothing here writes or calls a paid API.

It is a thin layer over `chunk_units`, which keeps the rules that matter:
- only the pages in `request.scope` (and the learner's own text) reach the model; the model names
  a page by label (`D1.p3`, `notes`), the CODE finds each quote in that page's text, and a draft
  left with no verified anchor is dropped;
- untrusted text enters the prompt only through `wrap_untrusted` (escaped, nonce-tagged block);
- a refusal names a rule, never source text (ADR-0013).

What this layer adds: the session-scoped input, one stable `draft_key` per draft, and outcomes
instead of exceptions for the cases T7.7 must handle without crashing: the AI cap
(`pending_ai`) and unusable model output (`ok` with no drafts and a `reason`). Over-size input and
duplicate pages still raise `ChunkInputError`: the caller splits the scope.

`draft_key = sha256(session_id \\0 quote_hash)`, where `quote_hash` covers the verified anchors
only (document, page, folded quote), sorted. The title and content, which the model may reword
between runs, are not part of it. The key is therefore stable for the same verified evidence;
T7.7 caches the result per submission so a redelivery does not ask again.
"""

import dataclasses
import hashlib
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict

from ai_service.domain.anchor_check import normalize_with_map
from ai_service.llm.quota import QuotaExceededError, QuotaUnavailableError
from ai_service.tasks.chunk_models import ChunkRequest as _ChunkRequest
from ai_service.tasks.chunk_models import (
    DocInput,
    Dropped,
    NewUnit,
    PageInput,
)
from ai_service.tasks.chunk_units import ChunkInvalidError, ChunkPrompt, chunk_units
from ai_service.tasks.grade import wrap_untrusted

TASK = "draft_units"
PROMPT_VERSION = "v1"
_PROMPTS = Path(__file__).resolve().parents[3] / "prompts"
_NONCE_PLACEHOLDER = "{{NONCE}}"
MAX_DESCRIPTION_CHARS = 500


def _no_nul(text: str) -> str:
    if "\x00" in text:
        raise ValueError("NUL")
    return text


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


class ScopedPage(_Strict):
    page_no: int
    text: Annotated[str, AfterValidator(_no_nul)]
    section_id: uuid.UUID | None = None


class ScopedDoc(_Strict):
    document_id: uuid.UUID
    name: Annotated[str, AfterValidator(_no_nul)]
    pages: list[ScopedPage]


class DraftRequest(_Strict):
    """What the learner declared: pages of documents, their own text, a one-line description."""

    session_id: uuid.UUID
    scope: list[ScopedDoc]
    submission_text: Annotated[str, AfterValidator(_no_nul)] | None = None
    description: Annotated[str, AfterValidator(_no_nul)] | None = None


@dataclass(frozen=True)
class DraftAnchor:
    # None for the learner's own text.
    document_id: uuid.UUID | None
    page: int | None
    # original[start:end] of the page text, never the string the model returned
    quote: str


@dataclass(frozen=True)
class Draft:
    draft_key: str
    title: str
    content: str
    section_ids: list[uuid.UUID]
    anchors: list[DraftAnchor]


@dataclass(frozen=True)
class DraftOutcome:
    status: Literal["ok", "pending_ai"]
    drafts: list[Draft]
    dropped: list[Dropped]
    # A fixed code, never source text: ai_cap | quota_unavailable | malformed_output |
    # empty_input | no_valid_anchor | no_units; None when drafts were made.
    reason: str | None = None


@lru_cache
def _system_template() -> str:
    return (_PROMPTS / TASK / f"{PROMPT_VERSION}.md").read_text("utf-8")


def _fold(text: str) -> str:
    return normalize_with_map(text)[0].strip().casefold()


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _draft_key(session_id: uuid.UUID, anchors: list[DraftAnchor]) -> str:
    parts = sorted(
        _sha(f"{a.document_id or 'notes'}|{a.page or 0}|{_fold(a.quote)}") for a in anchors
    )
    return _sha(f"{session_id}\0{_sha(chr(10).join(parts))}")


def _chunk_request(request: DraftRequest) -> _ChunkRequest:
    return _ChunkRequest(
        documents=[
            DocInput(
                document_id=doc.document_id,
                name=doc.name,
                pages=[PageInput(page_no=p.page_no, text=p.text) for p in doc.pages],
            )
            for doc in request.scope
        ],
        notes_text=request.submission_text,
    )


def _has_text(request: DraftRequest) -> bool:
    if request.submission_text and request.submission_text.strip():
        return True
    return any(p.text.strip() for doc in request.scope for p in doc.pages)


def _to_draft(
    session_id: uuid.UUID, unit: NewUnit, sections: dict[tuple[uuid.UUID, int], uuid.UUID]
) -> Draft:
    anchors = [DraftAnchor(a.document_id, a.page_no, a.quote_text) for a in unit.anchors]
    section_ids: list[uuid.UUID] = []
    for a in unit.anchors:
        section = sections.get((a.document_id, a.page_no)) if a.document_id and a.page_no else None
        if section is not None and section not in section_ids:
            section_ids.append(section)
    return Draft(
        draft_key=_draft_key(session_id, anchors),
        title=unit.title,
        content=unit.summary,
        section_ids=section_ids,
        anchors=anchors,
    )


def draft_units(request: DraftRequest, ask: Callable[[ChunkPrompt], str]) -> DraftOutcome:
    """Drafts for the declared scope. Raises only `ChunkInputError` (over-size, duplicate page)."""
    if not _has_text(request):
        return DraftOutcome("ok", [], [], "empty_input")
    description = (request.description or "").strip()[:MAX_DESCRIPTION_CHARS]

    def ask_with_draft_prompt(prompt: ChunkPrompt) -> str:
        system = _system_template().replace(_NONCE_PLACEHOLDER, prompt.nonce)
        user = prompt.user
        if description:
            # Escaped by wrap_untrusted, so it cannot close a block whatever it contains.
            block = wrap_untrusted("description", description, prompt.nonce, label="description")
            user = f"{user}\n\n{block}"
        return ask(dataclasses.replace(prompt, system=system, user=user))

    try:
        result = chunk_units(_chunk_request(request), ask_with_draft_prompt)
    except QuotaExceededError:
        return DraftOutcome("pending_ai", [], [], "ai_cap")
    except QuotaUnavailableError:
        return DraftOutcome("pending_ai", [], [], "quota_unavailable")
    except ChunkInvalidError:
        return DraftOutcome("ok", [], [], "malformed_output")

    sections = {
        (doc.document_id, p.page_no): p.section_id
        for doc in request.scope
        for p in doc.pages
        if p.section_id is not None
    }
    drafts: dict[str, Draft] = {}
    for unit in result.new_units:
        draft = _to_draft(request.session_id, unit, sections)
        kept = drafts.get(draft.draft_key)
        if kept is None:
            drafts[draft.draft_key] = draft
        else:  # same evidence under two titles: one draft
            drafts[draft.draft_key] = dataclasses.replace(
                kept,
                section_ids=kept.section_ids
                + [s for s in draft.section_ids if s not in kept.section_ids],
            )
    if drafts:
        return DraftOutcome("ok", list(drafts.values()), result.dropped)
    reason = "no_valid_anchor" if result.dropped else "no_units"
    return DraftOutcome("ok", [], result.dropped, reason)
