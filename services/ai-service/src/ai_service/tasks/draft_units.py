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

`draft_key` is the one of `session-result.v2` (`session_result_v2.draft_key`): the hash of the
session and of the FIRST anchor's quote. Anchors are put in a fixed order (document, page,
offset, the learner's notes last) so the first one does not depend on the order the model listed
them in. The title and content, which the model may reword between runs, are not part of it. The
key is stable for the same verified evidence; the handler caches the result per submission so a
redelivery does not ask again.
"""

import dataclasses
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from ai_service.llm.quota import QuotaExceededError, QuotaUnavailableError
from ai_service.messaging.session_result_v2 import draft_key as contract_draft_key
from ai_service.messaging.session_result_v2 import quote_hash as contract_quote_hash
from ai_service.tasks.chunk_models import ChunkRequest as _ChunkRequest
from ai_service.tasks.chunk_models import (
    DocInput,
    Dropped,
    Kind,
    NewUnit,
    PageInput,
)
from ai_service.tasks.chunk_units import (
    ChunkInputError,
    ChunkInvalidError,
    ChunkPrompt,
    chunk_units,
)
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
    page_no: Annotated[int, Field(ge=1)]
    text: Annotated[str, AfterValidator(_no_nul)]
    # A section can start mid-page, so a page may belong to several.
    section_ids: list[uuid.UUID] = []


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
    # Offsets of `quote` in the page text (or in the submitted text for the learner's own notes).
    start: int = 0
    end: int = 0

    @property
    def source(self) -> Literal["document", "notes"]:
        return "notes" if self.document_id is None else "document"


@dataclass(frozen=True)
class Draft:
    draft_key: str
    quote_hash: str
    title: str
    content: str
    kind: Kind
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


def _anchor_order(anchor: DraftAnchor) -> tuple[int, str, int, int]:
    return (
        1 if anchor.document_id is None else 0,
        str(anchor.document_id or ""),
        anchor.page or 0,
        anchor.start,
    )


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
    session_id: uuid.UUID, unit: NewUnit, sections: dict[tuple[uuid.UUID, int], list[uuid.UUID]]
) -> Draft:
    anchors = sorted(
        (DraftAnchor(a.document_id, a.page_no, a.quote_text, a.start, a.end) for a in unit.anchors),
        key=_anchor_order,
    )
    first_hash = contract_quote_hash(anchors[0].quote)
    section_ids: list[uuid.UUID] = []
    for a in unit.anchors:
        found = sections.get((a.document_id, a.page_no), []) if a.document_id and a.page_no else []
        section_ids.extend(s for s in found if s not in section_ids)
    return Draft(
        draft_key=contract_draft_key(session_id, first_hash),
        quote_hash=first_hash,
        title=unit.title,
        content=unit.summary,
        kind=unit.kind,
        section_ids=section_ids,
        anchors=anchors,
    )


def draft_units(request: DraftRequest, ask: Callable[[ChunkPrompt], str]) -> DraftOutcome:
    """Drafts for the declared scope. Raises only `ChunkInputError` (size, duplicate page, doc)."""
    ids = [doc.document_id for doc in request.scope]
    if len(set(ids)) != len(ids):
        raise ChunkInputError("duplicate_document")
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
        (doc.document_id, p.page_no): p.section_ids for doc in request.scope for p in doc.pages
    }
    drafts: dict[str, Draft] = {}
    for unit in result.new_units:
        draft = _to_draft(request.session_id, unit, sections)
        kept = drafts.get(draft.draft_key)
        if kept is None:
            drafts[draft.draft_key] = draft
        else:  # same evidence under two titles: one draft
            # The first anchor is the same in both, so the key stays the one of the union.
            known = {(a.document_id, a.page, a.start, a.end) for a in kept.anchors}
            extra = [
                a for a in draft.anchors if (a.document_id, a.page, a.start, a.end) not in known
            ]
            drafts[draft.draft_key] = dataclasses.replace(
                kept,
                anchors=sorted(kept.anchors + extra, key=_anchor_order),
                section_ids=kept.section_ids
                + [s for s in draft.section_ids if s not in kept.section_ids],
            )
    if drafts:
        return DraftOutcome("ok", list(drafts.values()), result.dropped)
    reason = "no_valid_anchor" if result.dropped else "no_units"
    return DraftOutcome("ok", [], result.dropped, reason)
