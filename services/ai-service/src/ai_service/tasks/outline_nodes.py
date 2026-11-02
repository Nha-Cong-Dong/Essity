"""Outline node shared by the DOCX and PPTX outlines (T7.3, v2 §5, US-13 AC1-AC2).

Like `syllabus.SyllabusNode`, but the unit is an estimated page (characters / 1800) for DOCX or
a slide for PPTX. Leaves are contiguous over 1..total weight, and a node's `weight` is the
units under it; a leaf with no text weighs 1 (Q-D). Nothing here logs a title or text.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal

# Characters per estimated page (v2 §16.1).
CHARS_PER_PAGE = 1800
CHUNK_PAGES = 10
MAX_NODES = 2000
MAX_LEVEL = 3

Unit = Literal["est_page", "slide"]
Source = Literal["headings", "sections", "slides", "llm_toc", "chunk10"]


@dataclass(frozen=True)
class OutlineNode:
    title: str
    # 0 for a chapter or section.
    level: int
    # Position in the tree, depth first from 0.
    ord: int
    # 1-based, inclusive, in `unit`.
    start: int
    end: int
    weight: int
    unit: Unit
    source: Source

    @property
    def temporary(self) -> bool:
        """A chunk10 or flat slide tree is a stand-in until the learner fixes the outline."""
        return self.source in ("chunk10", "slides")


def est_pages(chars: int) -> int:
    """Estimated pages of `chars` characters; a leaf with no text still counts 1."""
    return max(1, -(-chars // CHARS_PER_PAGE))


def tiles(nodes: Sequence[OutlineNode], total: int) -> bool:
    """The invariant every outline must meet: leaves contiguous over 1..total, none empty."""
    if not nodes or any(n.end < n.start or n.weight < 1 for n in nodes):
        return False
    leaves = [
        n for i, n in enumerate(nodes) if i + 1 == len(nodes) or nodes[i + 1].level <= n.level
    ]
    expected = 1
    for leaf in leaves:
        if leaf.start != expected:
            return False
        expected = leaf.end + 1
    return expected == total + 1


# `doc_section.source` has five values (US-13): headings and PowerPoint sections are both
# `heading`; the flat slide list is a stand-in like `chunk10`, so it is stored as that.
_CORE_SOURCE: dict[Source, str] = {
    "headings": "heading",
    "sections": "heading",
    "llm_toc": "llm_toc",
    "slides": "chunk10",
    "chunk10": "chunk10",
}


def outline_body(nodes: Sequence[OutlineNode]) -> dict[str, Any]:
    """The `outline.json` body core-api reads (nodes depth first, each with its parent's index),
    in the unit of the nodes."""
    parents: list[int | None] = []
    stack: list[int] = []
    for index, node in enumerate(nodes):
        del stack[node.level :]
        parents.append(stack[-1] if stack else None)
        stack.append(index)
    return {
        "unit": nodes[0].unit if nodes else "est_page",
        "nodes": [
            {
                "title": node.title,
                "parent": parent,
                "page_start": node.start,
                "page_end": node.end,
                "weight": node.weight,
                "source": _CORE_SOURCE[node.source],
            }
            for node, parent in zip(nodes, parents, strict=True)
        ],
    }
