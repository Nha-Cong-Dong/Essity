"""Which pages a learner meant (CARDS-V3, US-02).

An @mention that names a document without positions ("@Giáo trình phần 1.1.1" typed by hand, or
the whole document) reaches ai-service with null pages. This module finds the sections it means,
in two steps and never more than one model call per submission:

1. by number or by title, in code, against the outline core-api sent (titles and pages only);
2. when that finds nothing, one model call that sees the outline and the learner's words and
   answers with section labels.

The model's answer is untrusted: labels outside the outline are dropped, at most `MAX_PICKED`
stay, the learner's words and the titles reach the prompt only through `wrap_untrusted`, and the
pages that follow are capped by `MAX_SCOPE_PAGES` where they are read. Nothing here logs a title,
a note or a model answer (ADR-0013).
"""

import hashlib
import json
import re
import unicodedata
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Final

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ai_service.llm.system import render_system
from ai_service.messaging.submission_context import OutlineDocument, OutlineSection
from ai_service.tasks.grade import new_nonce, wrap_untrusted

TASK: Final = "pick_sections"
PROMPT_VERSION: Final = "v1"
_PROMPTS = Path(__file__).resolve().parents[3] / "prompts"
MAX_PICKED = 8
MAX_OUTLINE_LINES = 400
MAX_NOTE_CHARS = 4000
MAX_OUTPUT_CHARS = 2000

_NUM = r"\d+(?:\.\d+)*"
_KEYWORD = re.compile(rf"(?:phan|muc|chuong|section|chapter|bai|ch\.?)\s*({_NUM})")
_DOTTED = re.compile(r"(?<![\d.])(\d+(?:\.\d+)+)(?![\d])")


def fold(text: str) -> str:
    """Lower case, no diacritics, single spaces: what titles and notes are compared as."""
    plain = unicodedata.normalize("NFD", text.replace("đ", "d").replace("Đ", "D"))
    plain = "".join(c for c in plain if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", plain.lower()).strip()


def number_prefix(title: str) -> str | None:
    """The number a title starts with ("Chương 3. Mạng" -> "3", "1.1.1 Phép thử" -> "1.1.1")."""
    found = re.match(rf"(?:[a-z]+\.?\s+)?({_NUM})(?![0-9])", fold(title))
    return found.group(1) if found else None


def numbers_in(text: str, *, description: bool) -> list[str]:
    """Section numbers a text names: after a keyword ("phần 1.1.1"), and, in the learner's
    description only, a bare dotted number ("1.1.1")."""
    folded = fold(text)
    found = [m.group(1) for m in _KEYWORD.finditer(folded)]
    if description:
        found += [m.group(1) for m in _DOTTED.finditer(folded)]
    return list(dict.fromkeys(found))


@dataclass(frozen=True)
class Scope:
    document_id: uuid.UUID
    section_id: uuid.UUID
    first_page: int
    last_page: int


def _descendants(
    sections: Sequence[OutlineSection], section: OutlineSection
) -> list[OutlineSection]:
    out: list[OutlineSection] = []
    inside = False
    for item in sections:
        if item.section_id == section.section_id:
            inside = True
            continue
        if inside:
            if item.depth <= section.depth:
                break
            out.append(item)
    return out


def scope_of(document: OutlineDocument, section: OutlineSection) -> Scope | None:
    """The pages of a section: its own, or those of its sub-sections when it has none."""
    firsts = [section.first_page] if section.first_page else []
    lasts = [section.last_page] if section.last_page else []
    if not firsts or not lasts:
        kids = [s for s in _descendants(document.sections, section) if s.first_page and s.last_page]
        firsts = [s.first_page for s in kids if s.first_page]
        lasts = [s.last_page for s in kids if s.last_page]
    if not firsts or not lasts:
        return None
    return Scope(document.document_id, section.section_id, min(firsts), max(lasts))


def match_by_text(
    document: OutlineDocument, description: str | None, notes: str
) -> list[OutlineSection]:
    """Sections named by number (unique ones only: a repeated number is never guessed) or whose
    whole title appears in the learner's words."""
    numbers = numbers_in(description or "", description=True) + numbers_in(
        notes[:MAX_NOTE_CHARS], description=False
    )
    hits: list[OutlineSection] = []
    for number in dict.fromkeys(numbers):
        same = [s for s in document.sections if number_prefix(s.title) == number]
        if len(same) == 1:
            hits.append(same[0])
    if hits:
        return hits
    words = fold(f"{description or ''}\n{notes[:MAX_NOTE_CHARS]}")
    for section in document.sections:
        title = re.sub(rf"^(?:[a-z]+\.?\s+)?{_NUM}[.:)]?\s*", "", fold(section.title))
        if len(title) >= 6 and title in words:
            hits.append(section)
    return hits


# --- the model step -------------------------------------------------------------------------


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


class PickAnswer(_Strict):
    sections: Annotated[list[Annotated[str, Field(max_length=40)]], Field(max_length=40)]


OUTPUT_SCHEMA: Final[dict[str, Any]] = PickAnswer.model_json_schema()
Picked = tuple[OutlineDocument, OutlineSection]


@dataclass(frozen=True)
class PickPrompt:
    version: str
    sha256: str
    system: str
    user: str
    labels: dict[str, Picked]
    outline: list[tuple[str, str]]  # label, title: for the fake provider only
    words: str


def prompt_text() -> str:
    return (_PROMPTS / TASK / f"{PROMPT_VERSION}.md").read_text("utf-8")


def prompt_sha256() -> str:
    return hashlib.sha256(prompt_text().encode()).hexdigest()


def build_pick_prompt(
    documents: Sequence[OutlineDocument], description: str | None, notes: str
) -> PickPrompt | None:
    """None when there is nothing to choose from or nothing the learner wrote."""
    words = "\n\n".join(t for t in (description, notes[:MAX_NOTE_CHARS]) if t and t.strip())
    labels: dict[str, Picked] = {}
    lines: list[str] = []
    outline: list[tuple[str, str]] = []
    for d, document in enumerate(documents, 1):
        for s, section in enumerate(document.sections, 1):
            if len(lines) >= MAX_OUTLINE_LINES:
                break
            label = f"D{d}.S{s}"
            labels[label] = (document, section)
            outline.append((label, section.title))
            lines.append(f"{label} | {'  ' * min(section.depth, 4)}{section.title}")
    if not lines or not words:
        return None
    corpus = "\n".join([words, *lines])
    nonce = new_nonce()
    while nonce in corpus:
        nonce = new_nonce()
    user = "\n\n".join(
        [
            wrap_untrusted("outline", "\n".join(lines), nonce),
            wrap_untrusted("note", words, nonce),
        ]
    )
    return PickPrompt(
        PROMPT_VERSION,
        prompt_sha256(),
        render_system(prompt_text(), nonce),
        user,
        labels,
        outline,
        words,
    )


def check_pick(text: str, prompt: PickPrompt) -> list[Picked]:
    """The sections the answer names that exist in the outline that was sent; anything else
    (a foreign label, a repeat, a broken answer) is dropped."""
    if len(text) > MAX_OUTPUT_CHARS:
        return []
    try:
        answer = PickAnswer.model_validate_json(text)
    except ValidationError:
        return []
    out: list[Picked] = []
    seen: set[str] = set()
    for label in answer.sections:
        label = label.strip()
        found = prompt.labels.get(label)
        if found is None or label in seen or len(out) >= MAX_PICKED:
            continue
        seen.add(label)
        out.append(found)
    return out


def fake_pick_sections(request: Any) -> str:
    """Local and test only: the first section whose title is in the note (from `payload`)."""
    note = fold(str(request.payload.get("note", "")))
    for label, title in request.payload.get("outline", []):
        plain = fold(str(title))
        if len(plain) >= 6 and plain in note:
            return json.dumps({"sections": [label]})
    return json.dumps({"sections": []})
