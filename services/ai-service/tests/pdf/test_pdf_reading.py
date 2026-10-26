"""T3.4: the pdf/ interface on ordinary files — outline, page labels, text, render (ADR-0011).

No user story spec (M3). Every PDF is built in the test (tests/pdf/helpers.py).
"""

import io
import pickle
from typing import cast

import pytest
from PIL import Image

from ai_service.pdf import MAX_TITLE_CHARS, OutlineEntry, PdfError, PdfLimits, open_pdf
from tests.pdf.helpers import Bookmark, Page, make_pdf


def test_page_count_counts_every_page() -> None:
    with open_pdf(make_pdf([Page(text="a"), Page(text="b"), Page()])) as doc:
        assert doc.page_count == 3


def test_outline_is_flat_with_levels_and_zero_based_pages() -> None:
    data = make_pdf(
        [Page(text="1"), Page(text="2"), Page(text="3")],
        bookmarks=(
            Bookmark("Chương 1: Tổng quan", 0, (Bookmark("1.1 Mạng là gì", 1),)),
            Bookmark("Chương 2", 2),
        ),
    )
    with open_pdf(data) as doc:
        assert doc.get_outline() == [
            OutlineEntry(title="Chương 1: Tổng quan", level=0, page_index=0),
            OutlineEntry(title="1.1 Mạng là gì", level=1, page_index=1),
            OutlineEntry(title="Chương 2", level=0, page_index=2),
        ]


def test_pdf_without_bookmarks_has_an_empty_outline() -> None:
    with open_pdf(make_pdf([Page(text="slide")])) as doc:
        assert doc.get_outline() == []


def test_page_labels_follow_roman_then_arabic_numbering() -> None:
    """Front matter i, ii, then the book's page 1 is the file's third page (PRD §7.1b)."""
    data = make_pdf(
        [Page(text=str(i)) for i in range(5)],
        labels=[(0, 1, "/r", "", 1), (2, 4, "/D", "", 1)],
    )
    with open_pdf(data) as doc:
        assert doc.get_page_labels() == ["i", "ii", "1", "2", "3"]


def test_page_labels_with_uppercase_letters() -> None:
    data = make_pdf([Page(text=str(i)) for i in range(3)], labels=[(0, 2, "/A", "", 1)])
    with open_pdf(data) as doc:
        assert doc.get_page_labels() == ["A", "B", "C"]


def test_page_labels_keep_a_prefix_and_a_start_other_than_one() -> None:
    data = make_pdf([Page(text="a"), Page(text="b")], labels=[(0, 1, "/D", "A-", 40)])
    with open_pdf(data) as doc:
        assert doc.get_page_labels() == ["A-40", "A-41"]


def test_without_page_labels_there_are_none() -> None:
    """No /PageLabels: None, so the caller can tell "the printed number is unknown" from a
    real label "1" (PRD §7.1b asks which number the student means)."""
    with open_pdf(make_pdf([Page(text="a"), Page(text="b")])) as doc:
        assert doc.get_page_labels() is None


def test_extract_text_returns_the_text_layer() -> None:
    with open_pdf(make_pdf([Page(text="TCP three-way handshake: SYN, SYN-ACK, ACK")])) as doc:
        page = doc.extract_text(0)
    assert "SYN-ACK" in page.text
    assert page.needs_vision is False


def test_scanned_page_without_a_text_layer_needs_vision() -> None:
    """T4.7: a scanned page with no text is marked to be read from its image."""
    with open_pdf(make_pdf([Page(image=True)])) as doc:
        page = doc.extract_text(0)
    assert page.text == ""
    assert page.needs_vision is True


def test_a_page_with_only_a_stamped_page_number_still_needs_vision() -> None:
    """A scan with a digital page number added: a few characters is not a text layer."""
    with open_pdf(make_pdf([Page(image=True, text="12")])) as doc:
        assert doc.extract_text(0).needs_vision is True


def test_render_page_returns_a_png_whose_long_side_is_max_px() -> None:
    with open_pdf(make_pdf([Page(text="a", width=842, height=595)])) as doc:
        image = doc.render_page(0, max_px=400)
    assert image.width == 400
    assert image.height == round(400 * 595 / 842)
    with Image.open(io.BytesIO(image.png)) as png:
        assert png.format == "PNG"
        assert png.size == (image.width, image.height)


def test_long_text_on_one_page_is_cut_at_the_limit() -> None:
    with open_pdf(
        make_pdf([Page(text="A" * 500)]), limits=PdfLimits(max_text_chars_per_page=100)
    ) as doc:
        assert doc.extract_text(0).text == "A" * 100


def test_a_long_outline_title_is_cut() -> None:
    data = make_pdf([Page(text="a")], bookmarks=(Bookmark("T" * 2000, 0),))
    with open_pdf(data) as doc:
        assert doc.get_outline()[0].title == "T" * MAX_TITLE_CHARS


def test_results_pickle_for_a_child_process() -> None:
    """T4.7 may run pdf/ in a child process: what it returns must cross a pipe."""
    data = make_pdf([Page(text="a")], bookmarks=(Bookmark("C", 0),))
    with open_pdf(data) as doc:
        values = (doc.get_outline(), doc.extract_text(0), doc.render_page(0, max_px=50))
    assert pickle.loads(pickle.dumps(values)) == values
    with pytest.raises(PdfError) as error:
        open_pdf(b"")
    restored = pickle.loads(pickle.dumps(error.value))
    assert restored.code == "malformed"


def test_render_page_draws_the_page_content() -> None:
    """A scan renders as something other than a blank page."""
    with open_pdf(make_pdf([Page(image=True)])) as doc:
        image = doc.render_page(0, max_px=64)
    with Image.open(io.BytesIO(image.png)) as png:
        darkest, lightest = cast(tuple[int, int], png.convert("L").getextrema())
    assert darkest < lightest


@pytest.mark.parametrize("index", [-1, 1])
def test_page_index_out_of_range_is_a_pdf_error(index: int) -> None:
    with open_pdf(make_pdf([Page(text="a")])) as doc:
        with pytest.raises(PdfError) as text_error:
            doc.extract_text(index)
        with pytest.raises(PdfError) as render_error:
            doc.render_page(index, max_px=100)
    assert text_error.value.code == render_error.value.code == "page_out_of_range"


def test_a_closed_document_cannot_be_read() -> None:
    with open_pdf(make_pdf([Page(text="a")])) as doc:
        pass
    with pytest.raises(PdfError) as error:
        doc.extract_text(0)
    assert error.value.code == "closed"
