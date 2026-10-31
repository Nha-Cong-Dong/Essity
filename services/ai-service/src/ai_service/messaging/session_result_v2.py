"""session-result.v2 (T7.6, spec v2 §16.3), ai-service's own copy of
`contracts/files/session-result.v2`.

Not shared by import with core-api (ADR-0003). The drafts are for the learner to confirm: nothing
here reaches the core database before that. `draft_key` makes a draft addressable across retries.
"""

import hashlib
import re
import unicodedata
import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

_HASH = r"^[0-9a-f]{64}$"
Hash = Annotated[str, StringConstraints(pattern=_HASH)]
Id = uuid.UUID


def quote_hash(quote_text: str) -> str:
    """Hex SHA-256 of the quote after NFC, with whitespace folded to single spaces and trimmed."""
    folded = re.sub(r"\s+", " ", unicodedata.normalize("NFC", quote_text)).strip()
    return hashlib.sha256(folded.encode("utf-8")).hexdigest()


def draft_key(study_session_id: uuid.UUID, quote_hash_: str) -> str:
    """Hex SHA-256 of `"<study_session_id>:<quote_hash>"`: the same draft in the same session
    always has the same key, whichever process wrote it."""
    return hashlib.sha256(f"{study_session_id}:{quote_hash_}".encode()).hexdigest()


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, hide_input_in_errors=True)


class Anchor(_Closed):
    source: Literal["document", "notes"]
    document_id: Id | None
    page_no: Annotated[int, Field(ge=1)] | None
    start: Annotated[int, Field(ge=0)]
    end: Annotated[int, Field(ge=0)]
    quote_text: str


class Draft(_Closed):
    draft_key: Hash
    quote_hash: Hash
    title: Annotated[str, StringConstraints(min_length=1, max_length=200)]
    content: str
    kind: Literal["concept", "mechanism", "comparison", "formula", "example"]
    section_id: Id | None
    suggested_section_id: Id | None
    # Optional and additive: every section of the draft; `section_id` is its first (primary).
    section_ids: Annotated[list[Id], Field(min_length=1)] | None = None
    anchors: Annotated[list[Anchor], Field(min_length=1)]


class Dropped(_Closed):
    anchors: Annotated[int, Field(ge=0)]
    drafts: Annotated[int, Field(ge=0)]


class Skipped(_Closed):
    kind: Literal["page", "note"]
    ref: Annotated[int, Field(ge=0)]
    reason: Literal["no_text", "truncated", "needs_ocr", "unreadable"]


class SessionResultV2(_Closed):
    version: Literal[2]
    study_session_id: Id
    drafts: Annotated[list[Draft], Field(max_length=200)]
    dropped: Dropped
    skipped: list[Skipped]

    @model_validator(mode="after")
    def _keys_are_the_formula_and_unique(self) -> "SessionResultV2":
        keys: set[str] = set()
        for draft in self.drafts:
            if draft.quote_hash != quote_hash(draft.anchors[0].quote_text):
                raise ValueError("quote_hash is not the hash of the first anchor's quote")
            if draft.draft_key != draft_key(self.study_session_id, draft.quote_hash):
                raise ValueError("draft_key is not the hash of session and quote")
            if draft.section_ids is not None and draft.section_id != draft.section_ids[0]:
                raise ValueError("section_id is not the first of section_ids")
            if draft.draft_key in keys:
                raise ValueError("draft_key repeats")
            keys.add(draft.draft_key)
        return self


def parse_result(raw: str | bytes) -> SessionResultV2:
    """Validate a result file (JSON text). Raises `pydantic.ValidationError`."""
    return SessionResultV2.model_validate_json(raw)


__all__ = ["SessionResultV2", "draft_key", "parse_result", "quote_hash"]
