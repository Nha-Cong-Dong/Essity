"""T3.4: broken or hostile PDFs end in a PdfError with a stable code, never a crash or a hang.

T4.7 relies on this so that one bad upload cannot take the worker down.
"""

import io
import time
from typing import cast

import pytest
from pypdf import PdfWriter

from ai_service.pdf import PdfError, PdfLimits, open_pdf
from tests.pdf.helpers import Page, flate_bomb_pdf, giant_page_pdf, make_pdf


def _code(data: bytes, limits: PdfLimits | None = None) -> str:
    with pytest.raises(PdfError) as error:
        with open_pdf(data, limits=limits or PdfLimits()):
            pass
    return error.value.code


@pytest.mark.parametrize(
    "data",
    [b"", b"not a pdf at all", b"%PDF-1.7\n%garbage\n", make_pdf([Page(text="a")])[:200]],
    ids=["empty", "text", "header-only", "truncated"],
)
def test_a_file_that_is_not_a_readable_pdf_is_malformed(data: bytes) -> None:
    assert _code(data) == "malformed"


def test_a_file_over_the_size_limit_is_refused_before_parsing() -> None:
    assert _code(b"x" * 2048, PdfLimits(max_bytes=1024)) == "too_large"


def test_a_pdf_over_the_page_limit_is_refused() -> None:
    data = make_pdf([Page(text=str(i)) for i in range(4)])
    assert _code(data, PdfLimits(max_pages=3)) == "too_many_pages"


def test_a_pdf_with_no_pages_is_malformed() -> None:
    buffer = io.BytesIO()
    PdfWriter().write(buffer)
    assert _code(buffer.getvalue()) == "malformed"


def test_rendering_a_giant_page_stays_within_max_px() -> None:
    """A 200-inch page at 300 dpi would be 60000 px a side; the long side is capped."""
    with open_pdf(giant_page_pdf()) as doc:
        image = doc.render_page(0, max_px=500)
    assert max(image.width, image.height) == 500


def test_max_px_is_capped_by_the_limits() -> None:
    with open_pdf(make_pdf([Page(text="a")]), limits=PdfLimits(max_render_px=300)) as doc:
        image = doc.render_page(0, max_px=5000)
    assert max(image.width, image.height) == 300


def test_rendering_is_capped_by_the_total_pixel_count() -> None:
    """A square page at max_px=1000 would be 1 MP; a 10 000 px budget makes it 100 x 100."""
    data = make_pdf([Page(text="a", width=600, height=600)])
    with open_pdf(data, limits=PdfLimits(max_render_pixels=10_000)) as doc:
        image = doc.render_page(0, max_px=1000)
    assert image.width * image.height <= 10_000
    assert (image.width, image.height) == (100, 100)


def test_a_sliver_page_renders_at_least_one_pixel_wide() -> None:
    data = make_pdf([Page(text="a", width=1, height=14400)])
    with open_pdf(data) as doc:
        image = doc.render_page(0, max_px=500)
    assert image.height == 500
    assert image.width >= 1


def test_reading_after_the_deadline_is_a_deadline_error() -> None:
    """A cooperative deadline, checked before each page (it cannot stop C code mid-page)."""
    with open_pdf(make_pdf([Page(text="a")]), limits=PdfLimits(deadline_s=0)) as doc:
        with pytest.raises(PdfError) as text_error:
            doc.extract_text(0)
        with pytest.raises(PdfError) as render_error:
            doc.render_page(0, max_px=10)
    assert text_error.value.code == render_error.value.code == "deadline"


def _encrypted(data: bytes, *, user_password: str, algorithm: str) -> bytes:
    writer = PdfWriter(clone_from=io.BytesIO(data))
    writer.encrypt(user_password=user_password, owner_password="owner", algorithm=algorithm)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


@pytest.mark.parametrize("algorithm", ["RC4-128", "AES-128", "AES-256"])
def test_a_pdf_with_only_an_owner_password_opens(algorithm: str) -> None:
    """Slides "protected" against copying open without a password in any viewer, AES too."""
    from tests.pdf.helpers import Bookmark

    data = _encrypted(
        make_pdf(
            [Page(text="slide text")],
            bookmarks=(Bookmark("Chương 1", 0),),
            labels=[(0, 0, "/r", "", 1)],
        ),
        user_password="",
        algorithm=algorithm,
    )
    with open_pdf(data) as doc:
        assert "slide text" in doc.extract_text(0).text
        assert [entry.title for entry in doc.get_outline()] == ["Chương 1"]
        assert doc.get_page_labels() == ["i"]


@pytest.mark.parametrize("algorithm", ["RC4-128", "AES-256"])
def test_a_pdf_that_needs_a_password_to_open_is_encrypted(algorithm: str) -> None:
    data = _encrypted(make_pdf([Page(text="a")]), user_password="pw", algorithm=algorithm)
    assert _code(data) == "encrypted"


def test_a_compression_bomb_page_does_not_hang_text_extraction() -> None:
    """200 MB of spaces behind ~200 KB of Flate: reading the page finishes fast."""
    started = time.monotonic()
    with open_pdf(flate_bomb_pdf(200)) as doc:
        page = doc.extract_text(0)
        doc.render_page(0, max_px=100)
    assert page.text == ""
    assert time.monotonic() - started < 20


def test_an_outline_over_the_entry_limit_is_cut_not_failed() -> None:
    from tests.pdf.helpers import Bookmark

    data = make_pdf([Page(text="a")], bookmarks=tuple(Bookmark(f"Mục {i}", 0) for i in range(10)))
    with open_pdf(data, limits=PdfLimits(max_outline_entries=4)) as doc:
        assert [entry.title for entry in doc.get_outline()] == [f"Mục {i}" for i in range(4)]


def test_an_outline_deeper_than_the_depth_limit_drops_the_deeper_entries() -> None:
    from tests.pdf.helpers import Bookmark

    deep = Bookmark("L3", 0)
    for name in ("L2", "L1", "L0"):
        deep = Bookmark(name, 0, (deep,))
    with open_pdf(
        make_pdf([Page(text="a")], bookmarks=(deep,)), limits=PdfLimits(max_outline_depth=2)
    ) as doc:
        assert [(e.title, e.level) for e in doc.get_outline()] == [("L0", 0), ("L1", 1)]


def test_an_outline_that_loops_back_on_itself_terminates() -> None:
    """A hostile /Next pointing back at the first item must not loop forever."""
    from pypdf.generic import DictionaryObject, NameObject

    from tests.pdf.helpers import Bookmark

    data = make_pdf([Page(text="a")], bookmarks=(Bookmark("A", 0), Bookmark("B", 0)))
    writer = PdfWriter(clone_from=io.BytesIO(data))
    outlines = cast(DictionaryObject, writer.root_object["/Outlines"].get_object())
    last = cast(DictionaryObject, outlines["/Last"].get_object())
    last[NameObject("/Next")] = outlines.raw_get("/First")
    buffer = io.BytesIO()
    writer.write(buffer)
    with open_pdf(buffer.getvalue()) as doc:
        titles = [entry.title for entry in doc.get_outline()]
    assert titles == ["A", "B"]
