"""Outline of a DOCX (T7.3, US-13 AC1-AC2): the tree of its headings.

Pure: `build_docx_outline(content)` takes what `ai_service.docx.read_docx` returned. Sources:
  1. `headings`: Word headings (outline level, else a "Heading N" style), nested by level;
  2. `chunk10`: blocks of 10 estimated pages, a temporary tree, when the file has no heading.

Leaves tile 1..N in estimated pages (characters / 1800, a leaf with no text weighs 1); a node's
`weight` is the pages under it. A heading that has sub-headings and text of its own keeps that
text as a first child with the same title, so the leaves always tile. Never raises for what the
file holds: the worst case is the `chunk10` tree.
"""

from dataclasses import dataclass

from ai_service.docx import DocxContent
from ai_service.tasks.outline_nodes import (
    CHUNK_PAGES,
    MAX_LEVEL,
    MAX_NODES,
    OutlineNode,
    est_pages,
    tiles,
)

FRONT_MATTER_TITLE = "Front matter"


@dataclass
class _Entry:
    title: str
    level: int
    chars: int = 0


def _entries(content: DocxContent) -> list[_Entry]:
    entries: list[_Entry] = []
    front = _Entry(FRONT_MATTER_TITLE, 0)
    current = front
    previous = -1
    for paragraph in content.paragraphs:
        if paragraph.heading_level is None:
            current.chars += len(paragraph.text)
            continue
        level = min(paragraph.heading_level, previous + 1, MAX_LEVEL)
        previous = level
        current = _Entry(paragraph.text, level)
        entries.append(current)
    if front.chars > 0 and entries:
        entries.insert(0, front)
    return entries


def _tree(entries: list[_Entry]) -> list[OutlineNode]:
    # (title, level, chars or None for a node whose weight comes from its children)
    drafts: list[tuple[str, int, int | None]] = []
    for index, entry in enumerate(entries):
        has_children = index + 1 < len(entries) and entries[index + 1].level > entry.level
        if has_children:
            drafts.append((entry.title, entry.level, None))
            if entry.chars > 0:
                drafts.append((entry.title, entry.level + 1, entry.chars))
        else:
            drafts.append((entry.title, entry.level, entry.chars))
    weights = [est_pages(chars) if chars is not None else 0 for _, _, chars in drafts]
    nodes: list[OutlineNode] = []
    position = 1
    leaf_start: list[int] = []
    for weight in weights:
        leaf_start.append(position)
        position += weight
    for order, (title, level, chars) in enumerate(drafts):
        if chars is not None:
            start, weight = leaf_start[order], weights[order]
        else:
            end_index = order + 1
            while end_index < len(drafts) and drafts[end_index][1] > level:
                end_index += 1
            weight = sum(weights[order + 1 : end_index])
            start = leaf_start[order + 1]
        nodes.append(
            OutlineNode(
                title=title,
                level=level,
                ord=order,
                start=start,
                end=start + weight - 1,
                weight=weight,
                unit="est_page",
                source="headings",
            )
        )
    return nodes


def chunk10_est_pages(total_chars: int) -> list[OutlineNode]:
    pages = est_pages(total_chars)
    nodes: list[OutlineNode] = []
    for order, start in enumerate(range(0, pages, CHUNK_PAGES)):
        end = min(start + CHUNK_PAGES, pages)
        nodes.append(
            OutlineNode(
                title=f"Pages {start + 1}-{end}",
                level=0,
                ord=order,
                start=start + 1,
                end=end,
                weight=end - start,
                unit="est_page",
                source="chunk10",
            )
        )
    return nodes


def build_docx_outline(content: DocxContent) -> list[OutlineNode]:
    entries = _entries(content)
    if entries and len(entries) <= MAX_NODES:
        nodes = _tree(entries)
        total = sum(n.weight for n in nodes if n.level == 0)
        if len(nodes) <= MAX_NODES and tiles(nodes, total):
            return nodes
    return chunk10_est_pages(content.char_count)
