"""Small PDFs built in the test, so no binary fixture is committed (T3.4).

pypdf writes the file; text uses the standard Helvetica font, a "scan" is a page that only
draws an image, the way a scanner's output does.
"""

import io
import zlib
from dataclasses import dataclass, field

from pypdf import PdfWriter
from pypdf.generic import (
    ArrayObject,
    DecodedStreamObject,
    DictionaryObject,
    NameObject,
    NumberObject,
    StreamObject,
)


@dataclass(frozen=True)
class Page:
    text: str | None = None
    image: bool = False
    width: float = 595.0
    height: float = 842.0


@dataclass(frozen=True)
class Bookmark:
    title: str
    page: int
    children: tuple["Bookmark", ...] = field(default_factory=tuple["Bookmark", ...])


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _image(writer: PdfWriter) -> StreamObject:
    pixels = bytes((x * 32) % 256 for x in range(64 * 64))
    image = DecodedStreamObject()
    image.set_data(pixels)
    image.update(
        {
            NameObject("/Type"): NameObject("/XObject"),
            NameObject("/Subtype"): NameObject("/Image"),
            NameObject("/Width"): NumberObject(64),
            NameObject("/Height"): NumberObject(64),
            NameObject("/ColorSpace"): NameObject("/DeviceGray"),
            NameObject("/BitsPerComponent"): NumberObject(8),
        }
    )
    return image


def make_pdf(
    pages: list[Page],
    *,
    bookmarks: tuple[Bookmark, ...] = (),
    labels: list[tuple[int, int, str, str, int]] | None = None,
) -> bytes:
    """`labels`: (first page, last page, style, prefix, start) for pypdf's set_page_label,
    style one of /D /r /R /a /A."""
    writer = PdfWriter()
    font = writer._add_object(  # pyright: ignore[reportPrivateUsage]
        DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }
        )
    )
    for spec in pages:
        page = writer.add_blank_page(width=spec.width, height=spec.height)
        ops: list[str] = []
        resources = DictionaryObject()
        if spec.image:
            image = writer._add_object(_image(writer))  # pyright: ignore[reportPrivateUsage]
            resources[NameObject("/XObject")] = DictionaryObject({NameObject("/Im0"): image})
            ops.append(f"q {spec.width} 0 0 {spec.height} 0 0 cm /Im0 Do Q")
        if spec.text is not None:
            resources[NameObject("/Font")] = DictionaryObject({NameObject("/F1"): font})
            ops.append(f"BT /F1 12 Tf 40 {spec.height - 60} Td ({_escape(spec.text)}) Tj ET")
        content = DecodedStreamObject()
        content.set_data("\n".join(ops).encode("latin-1"))
        page[NameObject("/Resources")] = resources
        page[NameObject("/Contents")] = writer._add_object(content)  # pyright: ignore[reportPrivateUsage]

    def add(items: tuple[Bookmark, ...], parent: object | None) -> None:
        for item in items:
            ref = writer.add_outline_item(item.title, item.page, parent=parent)  # pyright: ignore[reportArgumentType]
            add(item.children, ref)

    add(bookmarks, None)
    for first, last, style, prefix, start in labels or []:
        writer.set_page_label(first, last, style=style, prefix=prefix or None, start=start)  # pyright: ignore[reportArgumentType]
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def flate_bomb_pdf(decoded_mb: int = 200) -> bytes:
    """One page whose content stream inflates to `decoded_mb` MB of spaces."""
    writer = PdfWriter()
    page = writer.add_blank_page(width=595, height=842)
    raw = zlib.compress(b" " * (decoded_mb * 1024 * 1024), 9)
    stream = StreamObject()
    stream._data = raw  # pyright: ignore[reportPrivateUsage, reportAttributeAccessIssue]
    stream[NameObject("/Filter")] = NameObject("/FlateDecode")
    page[NameObject("/Contents")] = writer._add_object(stream)  # pyright: ignore[reportPrivateUsage]
    page[NameObject("/Resources")] = DictionaryObject()
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def giant_page_pdf() -> bytes:
    """A page of 14400 x 14400 pt (the PDF maximum, 200 inches a side) with some text."""
    return make_pdf([Page(text="huge", width=14400, height=14400)])


__all__ = ["ArrayObject", "Bookmark", "Page", "flate_bomb_pdf", "giant_page_pdf", "make_pdf"]
