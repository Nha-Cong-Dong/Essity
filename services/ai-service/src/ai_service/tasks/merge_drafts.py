"""Merge drafts that say the same thing, and name the session (CARDS-V3, US-02).

Knowledge that comes from several sources (two documents, two notes, a page and a note) is drafted
once per batch, so the same idea can come out twice. One model call, at most per submission, reads
every candidate (title and summary only) and answers with GROUPS of candidate labels and a title
for the session by topic. That is all it can say:

- the code makes the merged draft: the title, content and kind of ONE candidate of the group (the
  one with the longest content), the union of every anchor and section of the group. The model can
  neither write card text nor add a quote (the cards go straight to the learner's vault, so no new
  sentence may enter without a verified quote behind it);
- a label that does not exist, repeats, or sits in two groups is ignored; a group of one is no
  group; at most `MAX_GROUP` candidates join one card;
- the session title is cleaned (control characters out, at most 200 characters); an unusable one
  falls back to the title of the first draft;
- any failure (cap, unavailable model, broken or oversized answer) leaves the candidates as they
  are: a merge is a convenience and never loses a card.

Untrusted text (candidate titles and summaries come from the learner's pages) reaches the prompt
only through `wrap_untrusted`. Nothing here logs text (ADR-0013).
"""

import dataclasses
import hashlib
import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Final

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ai_service.messaging.session_result_v2 import draft_key_for_set, quote_hash
from ai_service.tasks.draft_units import Draft, anchor_order
from ai_service.tasks.grade import new_nonce, wrap_untrusted

TASK: Final = "merge_drafts"
PROMPT_VERSION: Final = "v1"
_PROMPTS = Path(__file__).resolve().parents[3] / "prompts"
_NONCE = "{{NONCE}}"
MAX_CANDIDATES = 60
MAX_GROUP = 8
MAX_SUMMARY_CHARS = 600
MAX_OUTPUT_CHARS = 4000
MAX_TITLE_CHARS = 200


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


class MergeAnswer(_Strict):
    groups: Annotated[
        list[Annotated[list[Annotated[str, Field(max_length=12)]], Field(max_length=20)]],
        Field(max_length=MAX_CANDIDATES),
    ]
    title: Annotated[str, Field(max_length=1000)] | None = None


OUTPUT_SCHEMA: Final[dict[str, Any]] = MergeAnswer.model_json_schema()


@dataclass(frozen=True)
class MergePrompt:
    version: str
    sha256: str
    system: str
    user: str
    labels: dict[str, int]  # label -> index in the drafts sent
    candidates: list[tuple[str, str, str]]  # label, title, summary: for the fake provider only


def prompt_text() -> str:
    return (_PROMPTS / TASK / f"{PROMPT_VERSION}.md").read_text("utf-8")


def prompt_sha256() -> str:
    return hashlib.sha256(prompt_text().encode()).hexdigest()


def build_prompt(drafts: Sequence[Draft]) -> MergePrompt | None:
    """None when there is nothing to merge or name (no draft)."""
    sent = list(drafts)[:MAX_CANDIDATES]
    if not sent:
        return None
    candidates = [(f"C{n}", d.title, d.content[:MAX_SUMMARY_CHARS]) for n, d in enumerate(sent, 1)]
    corpus = "\n".join(f"{t}\n{s}" for _, t, s in candidates)
    nonce = new_nonce()
    while nonce in corpus:
        nonce = new_nonce()
    user = "\n\n".join(
        wrap_untrusted("candidate", f"{title}\n{summary}", nonce, label=label)
        for label, title, summary in candidates
    )
    return MergePrompt(
        PROMPT_VERSION,
        prompt_sha256(),
        prompt_text().replace(_NONCE, nonce),
        user,
        {label: n for n, (label, _, _) in enumerate(candidates)},
        candidates,
    )


_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]+")


def clean_title(text: str | None) -> str | None:
    if text is None:
        return None
    cleaned = re.sub(r"\s+", " ", _CONTROL.sub(" ", text)).strip()
    return cleaned[:MAX_TITLE_CHARS].strip() or None


def parse_answer(text: str, prompt: MergePrompt) -> tuple[list[list[int]], str | None]:
    """The groups (indices into the drafts sent, each at least two, none repeated) and the
    cleaned title. A broken or oversized answer is no groups and no title."""
    if len(text) > MAX_OUTPUT_CHARS:
        return [], None
    try:
        answer = MergeAnswer.model_validate_json(text)
    except ValidationError:
        return [], None
    used: set[int] = set()
    groups: list[list[int]] = []
    for labels in answer.groups:
        members: list[int] = []
        for label in labels:
            index = prompt.labels.get(label.strip())
            if index is None or index in used or index in members:
                continue
            members.append(index)
        if len(members) < 2:
            continue
        members = members[:MAX_GROUP]
        used.update(members)
        groups.append(members)
    return groups, clean_title(answer.title)


def key_of(session_id: Any, draft: Draft) -> str:
    """The key of a draft: the session and the SET of its anchors' quotes (one quote gives the
    key every draft had before merging existed)."""
    return draft_key_for_set(session_id, [quote_hash(a.quote) for a in draft.anchors])


def combine(group: Sequence[Draft]) -> Draft:
    """One draft from a group: the card text of the member with the longest content, every anchor
    and section of the group."""
    lead = max(group, key=lambda d: len(d.content))
    anchors: list[Any] = []
    seen: set[tuple[object, ...]] = set()
    sections: list[Any] = []
    for draft in group:
        for a in draft.anchors:
            ident = (a.document_id, a.page, a.start, a.end)
            if ident not in seen:
                seen.add(ident)
                anchors.append(a)
        sections.extend(s for s in draft.section_ids if s not in sections)
    anchors.sort(key=anchor_order)
    return dataclasses.replace(
        lead,
        anchors=anchors,
        quote_hash=quote_hash(anchors[0].quote),
        section_ids=sections,
    )


def apply_groups(drafts: Sequence[Draft], groups: Sequence[Sequence[int]]) -> list[Draft]:
    """The drafts with each group replaced, at the place of its first member, by its merge."""
    first_of = {g[0]: g for g in groups}
    inside = {i for g in groups for i in g}
    out: list[Draft] = []
    for index, draft in enumerate(drafts):
        if index in first_of:
            out.append(combine([drafts[i] for i in first_of[index]]))
        elif index not in inside:
            out.append(draft)
    return out


def fake_merge_drafts(request: Any) -> str:
    """Local and test only: candidates with the same title (folded) form a group; the title is
    the first candidate's."""
    by_title: dict[str, list[str]] = {}
    for label, title, _ in request.payload.get("candidates", []):
        by_title.setdefault(re.sub(r"\s+", " ", str(title)).strip().lower(), []).append(label)
    groups = [labels for labels in by_title.values() if len(labels) > 1]
    first = request.payload.get("candidates", [[None, None]])[0][1]
    return json.dumps({"groups": groups, "title": first})
