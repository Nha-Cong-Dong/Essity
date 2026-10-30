"""Outline of a DOCX and a PPTX (T7.3; US-13 AC1, AC2)."""

from collections.abc import Sequence

from ai_service.docx import read_docx
from ai_service.pptx import read_pptx
from ai_service.tasks.outline_docx import build_docx_outline
from ai_service.tasks.outline_nodes import CHARS_PER_PAGE, OutlineNode, tiles
from ai_service.tasks.outline_pptx import build_pptx_outline
from tests.office.helpers import make_docx, make_pptx

PAGE = "x" * CHARS_PER_PAGE


def shape(nodes: Sequence[OutlineNode]) -> list[tuple[str, int, int, int, int]]:
    return [(n.title, n.level, n.start, n.end, n.weight) for n in nodes]


def test_docx_nested_headings_tile_in_est_pages() -> None:  # US-13 AC1, AC2
    data = make_docx(
        [
            (1, "Ch1"),
            (2, "S1.1"),
            (None, PAGE * 2),
            (2, "S1.2"),
            (None, PAGE),
            (1, "Ch2"),
            (None, PAGE),
        ]
    )
    nodes = build_docx_outline(read_docx(data))
    assert shape(nodes) == [
        ("Ch1", 0, 1, 3, 3),
        ("S1.1", 1, 1, 2, 2),
        ("S1.2", 1, 3, 3, 1),
        ("Ch2", 0, 4, 4, 1),
    ]
    assert {n.source for n in nodes} == {"headings"}
    assert {n.unit for n in nodes} == {"est_page"}
    assert not any(n.temporary for n in nodes)
    assert tiles(nodes, 4)


def test_docx_heading_with_text_and_children_keeps_own_text_as_first_child() -> None:
    data = make_docx([(1, "Ch"), (None, PAGE), (2, "Sub"), (None, PAGE)])
    nodes = build_docx_outline(read_docx(data))
    assert shape(nodes) == [
        ("Ch", 0, 1, 2, 2),
        ("Ch", 1, 1, 1, 1),
        ("Sub", 1, 2, 2, 1),
    ]


def test_docx_front_matter_before_first_heading() -> None:
    nodes = build_docx_outline(read_docx(make_docx([(None, "intro"), (1, "Ch"), (None, "t")])))
    assert [n.title for n in nodes] == ["Front matter", "Ch"]
    assert tiles(nodes, 2)


def test_docx_heading_levels_that_jump_are_repaired() -> None:
    nodes = build_docx_outline(read_docx(make_docx([(3, "deep first"), (1, "next")])))
    assert [(n.title, n.level) for n in nodes] == [("deep first", 0), ("next", 0)]


def test_docx_heading_without_text_weighs_one() -> None:  # US-13 AC1 (weight = 1)
    nodes = build_docx_outline(read_docx(make_docx([(1, "A"), (1, "B")])))
    assert [n.weight for n in nodes] == [1, 1]


def test_docx_without_headings_is_chunk10_est_pages() -> None:  # US-13 AC2
    data = make_docx([(None, PAGE * 12)])
    nodes = build_docx_outline(read_docx(data))
    assert shape(nodes) == [("Pages 1-10", 0, 1, 10, 10), ("Pages 11-12", 0, 11, 12, 2)]
    assert all(n.source == "chunk10" and n.temporary for n in nodes)


def test_docx_without_any_text_is_one_node_of_weight_one() -> None:  # US-13 AC1
    nodes = build_docx_outline(read_docx(make_docx([])))
    assert shape(nodes) == [("Pages 1-1", 0, 1, 1, 1)]


def test_pptx_without_sections_is_flat_and_temporary() -> None:  # US-13 AC2
    nodes = build_pptx_outline(read_pptx(make_pptx([("One", "x"), (None, None)])))
    assert shape(nodes) == [("One", 0, 1, 1, 1), ("Slide 2", 0, 2, 2, 1)]
    assert all(n.unit == "slide" and n.source == "slides" and n.temporary for n in nodes)


def test_pptx_sections_are_parents_of_slide_leaves() -> None:  # US-13 AC2
    data = make_pptx([("a", None), ("b", None), ("c", None)], [("S1", [1, 2]), ("S2", [3])])
    nodes = build_pptx_outline(read_pptx(data))
    assert shape(nodes) == [
        ("S1", 0, 1, 2, 2),
        ("a", 1, 1, 1, 1),
        ("b", 1, 2, 2, 1),
        ("S2", 0, 3, 3, 1),
        ("c", 1, 3, 3, 1),
    ]
    assert not any(n.temporary for n in nodes)


def test_pptx_sections_not_covering_slides_fall_back_to_flat() -> None:
    data = make_pptx([("a", None), ("b", None)], [("S1", [1])])
    nodes = build_pptx_outline(read_pptx(data))
    assert [n.source for n in nodes] == ["slides", "slides"]


def test_pptx_empty_deck_has_no_nodes() -> None:
    assert build_pptx_outline(read_pptx(make_pptx([]))) == []
