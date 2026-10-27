"""T3.4 (final review 🟠1/🟠2): bookmark titles and page labels are strings PDFium builds
from the file. Broken UTF-16 must not escape as UnicodeDecodeError, and a huge title or label
prefix must be refused by its size before it is copied into memory.
"""

import io
import time
from typing import cast

import pytest
from pypdf import PdfWriter
from pypdf.generic import (
    ArrayObject,
    ByteStringObject,
    DictionaryObject,
    NameObject,
    NumberObject,
    TextStringObject,
)

from ai_service.pdf import PdfError, PdfLimits, open_pdf
from tests.pdf.helpers import Bookmark, Page, make_pdf

# A UTF-16BE string holding half of a surrogate pair: no valid text decodes from it.
LONE_SURROGATE = ByteStringObject(bytes.fromhex("feffd8000041"))


def _write(writer: PdfWriter) -> bytes:
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def _bookmarks(writer: PdfWriter) -> list[DictionaryObject]:
    outlines = cast(DictionaryObject, writer.root_object["/Outlines"].get_object())
    node = cast(DictionaryObject, outlines["/First"].get_object())
    nodes = [node]
    while "/Next" in node:
        node = cast(DictionaryObject, node["/Next"].get_object())
        nodes.append(node)
    return nodes


def _with_labels(data: bytes, nums: list[tuple[int, DictionaryObject]]) -> bytes:
    """Replace /PageLabels with a number tree of exactly `nums` (no implied range at 0)."""
    writer = PdfWriter(clone_from=io.BytesIO(data))
    flat = ArrayObject()
    for page, label in nums:
        flat.extend([NumberObject(page), label])
    writer.root_object[NameObject("/PageLabels")] = DictionaryObject({NameObject("/Nums"): flat})
    return _write(writer)


def _label(style: str | None = None, prefix: object | None = None) -> DictionaryObject:
    label = DictionaryObject()
    if style is not None:
        label[NameObject("/S")] = NameObject(style)
    if prefix is not None:
        label[NameObject("/P")] = prefix  # pyright: ignore[reportArgumentType]
    return label


def test_a_bookmark_title_with_broken_utf16_is_read_with_replacement_characters() -> None:
    writer = PdfWriter(
        clone_from=io.BytesIO(make_pdf([Page(text="a")], bookmarks=(Bookmark("x", 0),)))
    )
    _bookmarks(writer)[0][NameObject("/Title")] = LONE_SURROGATE
    with open_pdf(_write(writer)) as doc:
        [entry] = doc.get_outline()
    assert "�" in entry.title


def test_a_page_label_with_broken_utf16_is_read_with_replacement_characters() -> None:
    data = _with_labels(make_pdf([Page(text="a")]), [(0, _label(prefix=LONE_SURROGATE))])
    with open_pdf(data) as doc:
        labels = doc.get_page_labels()
    assert labels is not None
    assert "�" in labels[0]


def test_a_huge_bookmark_title_is_dropped_without_being_copied() -> None:
    """20 bookmarks sharing one 2 MB title: each copy took ~0.3 s per MB and PDFium ran out
    of memory at 1000 of them; over the cap the title is empty and the entry kept."""
    data = make_pdf([Page(text="a")], bookmarks=tuple(Bookmark(f"x{i}", 0) for i in range(20)))
    writer = PdfWriter(clone_from=io.BytesIO(data))
    big = writer._add_object(TextStringObject("T" * (2 * 1024 * 1024)))  # pyright: ignore[reportPrivateUsage]
    for node in _bookmarks(writer):
        node[NameObject("/Title")] = big
    started = time.monotonic()
    with open_pdf(_write(writer)) as doc:
        outline = doc.get_outline()
    assert [entry.title for entry in outline] == [""] * 20
    assert time.monotonic() - started < 10


def test_a_huge_page_label_prefix_leaves_the_labels_unknown() -> None:
    """A 100 KB prefix repeated on every page would cost prefix x pages of memory."""
    data = _with_labels(
        make_pdf([Page(text=str(i)) for i in range(50)]),
        [(0, _label("/D", TextStringObject("P" * 100_000)))],
    )
    with open_pdf(data) as doc:
        assert doc.get_page_labels() is None


def test_pages_before_the_first_label_range_get_their_file_number() -> None:
    """/Nums starting at page 2 (the standard requires page 0): PDFium labels the uncovered
    pages with their 1-based file number."""
    data = _with_labels(make_pdf([Page(text=str(i)) for i in range(4)]), [(2, _label("/D"))])
    with open_pdf(data) as doc:
        assert doc.get_page_labels() == ["1", "2", "1", "2"]


def test_a_bookmark_to_a_page_that_is_gone_has_no_page() -> None:
    data = make_pdf([Page(text="a"), Page(text="b")], bookmarks=(Bookmark("to b", 1),))
    writer = PdfWriter(clone_from=io.BytesIO(data))
    writer.remove_page(1)
    with open_pdf(_write(writer)) as doc:
        [entry] = doc.get_outline()
    assert entry.title == "to b"
    assert entry.page_index is None


def test_outline_and_labels_stop_at_the_deadline() -> None:
    data = make_pdf([Page(text="a")], bookmarks=(Bookmark("C", 0),), labels=[(0, 0, "/r", "", 1)])
    with open_pdf(data, limits=PdfLimits(deadline_s=0)) as doc:
        with pytest.raises(PdfError) as outline_error:
            doc.get_outline()
        with pytest.raises(PdfError) as labels_error:
            doc.get_page_labels()
    assert outline_error.value.code == labels_error.value.code == "deadline"
