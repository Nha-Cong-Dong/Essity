"""Outline of a PPTX (T7.3, US-13 AC1-AC2): every slide is a leaf (unit = slide, weight 1, also
for a slide with no text, Q-D).

Pure: `build_pptx_outline(content)` takes what `ai_service.pptx.read_pptx` returned. Sources:
  1. `sections`: each PowerPoint section is a parent, its slides the leaves;
  2. `slides`: no section, so a flat list of slides in order, shown as temporary (a model may
     name the parts from the slide titles later, T9.8).

A leaf is titled by the slide's title, else "Slide N". Never raises for what the file holds: when
the sections do not cover the slides exactly once, the flat list is used.
"""

from ai_service.pptx import PptxContent
from ai_service.tasks.outline_nodes import MAX_NODES, OutlineNode, tiles


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


def build_pptx_outline(content: PptxContent) -> list[OutlineNode]:
    total = len(content.slides)
    if total == 0:
        return []
    nodes = _by_section(content) if content.sections else None
    if nodes and len(nodes) <= MAX_NODES and tiles(nodes, total):
        return nodes
    return _flat(content)
