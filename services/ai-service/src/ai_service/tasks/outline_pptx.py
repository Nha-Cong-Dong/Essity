"""Outline of a PPTX (T7.3, US-13 AC1-AC2): every slide is a leaf (unit = slide, weight 1, also
for a slide with no text, Q-D).

Pure: `build_pptx_outline(content)` takes what `ai_service.pptx.read_pptx` returned. Sources:
  1. `sections`: each PowerPoint section is a parent, its slides the leaves;
  2. `llm_toc` (T9.8): no section, so ONE model call over the slide titles alone names the
     parts; each part is a parent of its slides. Skipped (no call) when fewer than two slides
     have a title or more than `MAX_TITLES` do;
  3. `slides`: a flat list of slides in order, shown as temporary: the fallback for every failure
     of the model or its output.

A leaf is titled by the slide's title, else "Slide N". Never raises for what the file holds: when
the sections do not cover the slides exactly once, the flat list is used.
"""

import hashlib
import json
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, replace
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, ValidationError

from ai_service.llm.types import LlmRequest
from ai_service.pptx import PptxContent
from ai_service.tasks.grade import new_nonce, wrap_untrusted
from ai_service.tasks.outline_nodes import MAX_NODES, OutlineNode, tiles

_log = logging.getLogger(__name__)

# T9.8 reuses the T7.4 task name: same kind of work (names for parts of a document), same quota.
TASK = "syllabus_toc"
PROMPT_VERSION = "v1"
_PROMPTS = Path(__file__).resolve().parents[3] / "prompts"
_NONCE_PLACEHOLDER = "{{NONCE}}"
MAX_TITLES = 500
MAX_GROUPS = 100
MAX_GROUP_TITLE_CHARS = 200
MAX_OUTPUT_CHARS = 50_000


def _leaf(title: str | None, number: int, level: int, order: int, source: str) -> OutlineNode:
    return OutlineNode(
        title=title or f"Slide {number}",
        level=level,
        ord=order,
        start=number,
        end=number,
        weight=1,
        unit="slide",
        source="sections" if source == "sections" else "slides",
    )


def _flat(content: PptxContent) -> list[OutlineNode]:
    return [_leaf(s.title, s.number, 0, i, "slides") for i, s in enumerate(content.slides)]


def _by_section(content: PptxContent) -> list[OutlineNode] | None:
    titles = {s.number: s.title for s in content.slides}
    nodes: list[OutlineNode] = []
    for section in content.sections:
        if not section.slides:
            continue
        nodes.append(
            OutlineNode(
                title=section.name,
                level=0,
                ord=len(nodes),
                start=min(section.slides),
                end=max(section.slides),
                weight=len(section.slides),
                unit="slide",
                source="sections",
            )
        )
        for number in section.slides:
            nodes.append(_leaf(titles.get(number), number, 1, len(nodes), "sections"))
    return nodes or None


def _not_blank(text: str) -> str:
    if not text.strip() or "\x00" in text:
        raise ValueError("blank")
    return text


class _Group(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    title: Annotated[str, AfterValidator(_not_blank), Field(max_length=MAX_GROUP_TITLE_CHARS)]
    first_slide: Annotated[int, Field(ge=1, le=100_000)]


class _Groups(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    groups: Annotated[list[_Group], Field(min_length=1, max_length=MAX_GROUPS)]


OUTPUT_SCHEMA: dict[str, Any] = _Groups.model_json_schema()


@dataclass(frozen=True)
class TitlesPrompt:
    system: str
    user: str
    output_schema: dict[str, Any]
    nonce: str


@lru_cache
def system_template() -> str:
    return (_PROMPTS / "outline_pptx_titles" / f"{PROMPT_VERSION}.md").read_text("utf-8")


def prompt_sha256() -> str:
    return hashlib.sha256(system_template().encode()).hexdigest()


def _line(title: str) -> str:
    return re.sub(r"\s+", " ", title).strip()


def build_titles_prompt(content: PptxContent) -> TitlesPrompt | None:
    """Slide numbers and titles only; None when there is nothing worth a call."""
    titled = [(s.number, _line(s.title)) for s in content.slides if s.title and _line(s.title)]
    if len(titled) < 2 or len(titled) > MAX_TITLES:
        return None
    body = "\n".join(f"{number}\t{title}" for number, title in titled)
    nonce = new_nonce()
    while nonce in body:
        nonce = new_nonce()
    user = wrap_untrusted("slide_titles", body, nonce)
    return TitlesPrompt(
        system_template().replace(_NONCE_PLACEHOLDER, nonce), user, OUTPUT_SCHEMA, nonce
    )


def _grouped(content: PptxContent, groups: list[_Group]) -> list[OutlineNode] | None:
    total = len(content.slides)
    starts = [g.first_slide for g in groups]
    if starts[0] != 1 or starts != sorted(set(starts)) or starts[-1] > total:
        return None
    ends = [*(s - 1 for s in starts[1:]), total]
    nodes: list[OutlineNode] = []
    for group, start, end in zip(groups, starts, ends, strict=True):
        nodes.append(
            OutlineNode(
                title=_line(group.title)[:MAX_GROUP_TITLE_CHARS],
                level=0,
                ord=len(nodes),
                start=start,
                end=end,
                weight=end - start + 1,
                unit="slide",
                source="llm_toc",
            )
        )
        for slide in content.slides[start - 1 : end]:
            leaf = _leaf(slide.title, slide.number, 1, len(nodes), "slides")
            nodes.append(replace(leaf, source="llm_toc"))
    return nodes


def _from_titles(
    content: PptxContent, ask: Callable[[TitlesPrompt], str]
) -> list[OutlineNode] | None:
    prompt = build_titles_prompt(content)
    if prompt is None:
        return None
    try:
        text = ask(prompt)  # exactly one call, no retry
    except Exception as error:  # quota, provider, network: the type only
        _log.warning("pptx titles call failed", extra={"outcome": type(error).__name__})
        return None
    try:
        if len(text) > MAX_OUTPUT_CHARS:
            raise ValueError("too_long")
        groups = _Groups.model_validate_json(text).groups
    except (ValidationError, ValueError):
        _log.warning("pptx titles output refused")
        return None
    nodes = _grouped(content, groups)
    if nodes and len(nodes) <= MAX_NODES and tiles(nodes, len(content.slides)):
        return nodes
    _log.warning("pptx titles output unusable")
    return None


def build_pptx_outline(
    content: PptxContent, ask: Callable[[TitlesPrompt], str] | None = None
) -> list[OutlineNode]:
    total = len(content.slides)
    if total == 0:
        return []
    nodes = _by_section(content) if content.sections else None
    if nodes and len(nodes) <= MAX_NODES and tiles(nodes, total):
        return nodes
    if ask is not None:
        grouped = _from_titles(content, ask)
        if grouped:
            return grouped
    return _flat(content)


def fake_titles(request: LlmRequest | None = None) -> str:
    """The fake provider's answer: one part for the whole deck is not a grouping worth keeping,
    so it names none and the outline stays flat."""
    return json.dumps({"groups": []})
