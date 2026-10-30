"""docx/ and pptx/ reading and limits (T7.3; US-13 AC1, AC2; US-02 AC2)."""

import pytest

from ai_service.docx import DocxError, DocxLimits, read_docx
from ai_service.office_zip import ZipLimits
from ai_service.pptx import PptxError, PptxLimits, read_pptx
from tests.office.helpers import (
    make_docx,
    make_docx_with_table,
    make_pptx,
    with_extra_part,
    zip_bomb,
)


def test_docx_headings_by_style_nest_and_anchor() -> None:  # US-13 AC2
    data = make_docx([(1, "Chapter"), (None, "text a"), (2, "Section"), (None, "text b")])
    paragraphs = read_docx(data).paragraphs
    assert [(p.text, p.heading_level, p.anchor) for p in paragraphs] == [
        ("Chapter", 0, "Chapter"),
        ("text a", None, "Chapter"),
        ("Section", 1, "Section"),
        ("text b", None, "Section"),
    ]


def test_docx_headings_by_outline_level() -> None:  # US-13 AC2
    data = make_docx([(1, "A"), (2, "B")], outline_lvl=True)
    assert [p.heading_level for p in read_docx(data).paragraphs] == [0, 1]


def test_docx_text_before_first_heading_has_no_anchor() -> None:
    paragraphs = read_docx(make_docx([(None, "lead"), (1, "H")])).paragraphs
    assert paragraphs[0].anchor is None


def test_docx_table_text_is_in_reading_order() -> None:  # US-02 AC2
    texts = [p.text for p in read_docx(make_docx_with_table()).paragraphs]
    assert texts == ["Intro", "before table", "cell A", "cell B", "after table"]


def test_docx_garbage_is_malformed() -> None:
    with pytest.raises(DocxError) as raised:
        read_docx(b"not a zip")
    assert raised.value.code == "malformed"


def test_docx_too_large_is_refused() -> None:
    limits = DocxLimits(zip=ZipLimits(max_bytes=100))
    with pytest.raises(DocxError) as raised:
        read_docx(make_docx([(1, "A")]), limits)
    assert raised.value.code == "too_large"


def test_docx_zip_bomb_is_refused() -> None:
    with pytest.raises(DocxError) as raised:
        read_docx(zip_bomb(make_docx([(1, "A")]), 20 * 1024 * 1024))
    assert raised.value.code == "zip_bomb"


def test_docx_total_inflated_size_is_refused() -> None:
    limits = DocxLimits(zip=ZipLimits(max_uncompressed_bytes=1000))
    with pytest.raises(DocxError) as raised:
        read_docx(make_docx([(1, "A")]), limits)
    assert raised.value.code == "zip_bomb"


def test_docx_with_macros_is_refused() -> None:
    data = with_extra_part(make_docx([(1, "A")]), "word/vbaProject.bin")
    with pytest.raises(DocxError) as raised:
        read_docx(data)
    assert raised.value.code == "macros"


def test_docx_paragraph_limit() -> None:
    with pytest.raises(DocxError) as raised:
        read_docx(make_docx([(None, "a"), (None, "b")]), DocxLimits(max_paragraphs=1))
    assert raised.value.code == "too_many_blocks"


def test_pptx_slides_in_order_with_titles() -> None:  # US-13 AC2
    content = read_pptx(make_pptx([("One", "body 1"), ("Two", "body 2")]))
    assert [(s.number, s.title, s.text) for s in content.slides] == [
        (1, "One", "One\nbody 1"),
        (2, "Two", "Two\nbody 2"),
    ]
    assert content.sections == ()


def test_pptx_slide_without_text() -> None:
    content = read_pptx(make_pptx([(None, None)]))
    assert content.slides[0].title is None
    assert content.slides[0].text == ""


def test_pptx_sections_are_read() -> None:
    data = make_pptx([("a", None), ("b", None), ("c", None)], [("S1", [1, 2]), ("S2", [3])])
    content = read_pptx(data)
    assert [(s.name, s.slides) for s in content.sections] == [("S1", (1, 2)), ("S2", (3,))]


def test_pptx_garbage_is_malformed() -> None:
    with pytest.raises(PptxError) as raised:
        read_pptx(b"not a zip")
    assert raised.value.code == "malformed"


def test_pptx_slide_limit() -> None:
    with pytest.raises(PptxError) as raised:
        read_pptx(make_pptx([("a", None), ("b", None)]), PptxLimits(max_slides=1))
    assert raised.value.code == "too_many_slides"


def test_pptx_zip_bomb_and_macros_are_refused() -> None:
    data = make_pptx([("a", None)])
    with pytest.raises(PptxError) as bomb:
        read_pptx(zip_bomb(data, 20 * 1024 * 1024))
    assert bomb.value.code == "zip_bomb"
    with pytest.raises(PptxError) as macro:
        read_pptx(with_extra_part(data, "ppt/vbaProject.bin"))
    assert macro.value.code == "macros"
