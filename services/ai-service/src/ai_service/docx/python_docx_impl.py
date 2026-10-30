"""docx/ on python-docx (ADR-0011, T7.3): paragraphs in reading order, headings marked.

Nothing here runs macros or follows links: the file is parsed as XML only, and a macro-enabled
file is refused by `office_zip.check_zip` first. Headings come from `w:outlineLvl` (on the
paragraph, else on its style chain), else from a built-in "Heading N" style.
"""

# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportUnknownArgumentType=false
# pyright: reportPrivateUsage=false, reportAttributeAccessIssue=false
# pyright: reportOptionalMemberAccess=false

import io
import re
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph as DocxParagraph

from ai_service.docx.types import (
    MAX_HEADING_LEVEL,
    MAX_TITLE_CHARS,
    DocxError,
    DocxLimits,
    Paragraph,
)
from ai_service.office_zip import check_zip

_HEADING_STYLE = re.compile(r"^heading\s*([1-9])$", re.I)
_BASE_DEPTH = 8
# w:outlineLvl 9 is "body text".
_BODY_LEVEL = 9
_LIBRARY_ERRORS = (KeyError, ValueError, AttributeError, TypeError, OSError, IndexError)


@dataclass(frozen=True)
class DocxContent:
    paragraphs: tuple[Paragraph, ...]

    @property
    def char_count(self) -> int:
        return sum(len(p.text) for p in self.paragraphs)


def _outline_level(element: Any) -> int | None:
    values = element.xpath("./w:pPr/w:outlineLvl/@w:val")
    if not values:
        return None
    try:
        return int(values[0])
    except ValueError:
        return None


def _heading_level(paragraph: DocxParagraph) -> int | None:
    """0-based heading level, or None for body text."""
    level = _outline_level(paragraph._p)
    if level is None:
        style = paragraph.style
        for _ in range(_BASE_DEPTH):
            if style is None:
                break
            level = _outline_level(style.element)
            if level is None:
                match = _HEADING_STYLE.match(style.style_id or "") or _HEADING_STYLE.match(
                    style.name or ""
                )
                if match:
                    level = int(match.group(1)) - 1
            if level is not None:
                break
            style = style.base_style
    if level is None or not 0 <= level < _BODY_LEVEL:
        return None
    return min(level, MAX_HEADING_LEVEL)


def _blocks(document: Any) -> Iterator[DocxParagraph]:
    """Paragraphs of the body in reading order; a table contributes its cells row by row."""
    for item in document.iter_inner_content():
        if isinstance(item, Table):
            seen: set[int] = set()
            for row in item.rows:
                for cell in row.cells:
                    if id(cell._tc) in seen:  # a merged cell appears once per column it spans
                        continue
                    seen.add(id(cell._tc))
                    yield from cell.paragraphs
        else:
            yield item


def read_docx(data: bytes, limits: DocxLimits | None = None) -> DocxContent:
    """Paragraphs of a DOCX with heading levels and anchors. Raises DocxError with code
    too_large, zip_bomb, malformed, macros or too_many_blocks."""
    limits = limits or DocxLimits()
    check_zip(data, limits.zip, "word/document.xml")
    try:
        document = Document(io.BytesIO(data))
        paragraphs: list[Paragraph] = []
        anchor: str | None = None
        chars = 0
        for source in _blocks(document):
            text = source.text.strip()
            if not text:
                continue
            level = _heading_level(source)
            if level is not None:
                text = re.sub(r"\s+", " ", text)[:MAX_TITLE_CHARS]
                anchor = text
            paragraphs.append(Paragraph(text=text, heading_level=level, anchor=anchor))
            chars += len(text)
            if len(paragraphs) > limits.max_paragraphs or chars > limits.max_chars:
                raise DocxError("too_many_blocks")
    except DocxError:
        raise
    except _LIBRARY_ERRORS as error:
        raise DocxError("malformed") from error
    return DocxContent(paragraphs=tuple(paragraphs))
