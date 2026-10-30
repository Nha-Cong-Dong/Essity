"""pptx/ on python-pptx (ADR-0011, T7.3): slides in order, text in shape-tree order, sections.

Shape-tree order is the order PowerPoint reads aloud and the author's own stacking, so it is
the reading order (a group is read where it sits). Nothing here runs macros; a macro-enabled
file is refused by `office_zip.check_zip` first.
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

from lxml import etree
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE

from ai_service.office_zip import check_zip
from ai_service.pptx.types import (
    MAX_TITLE_CHARS,
    PptxError,
    PptxLimits,
    Section,
    Slide,
)

_NS = {"p14": "http://schemas.microsoft.com/office/powerpoint/2010/main"}
_LIBRARY_ERRORS = (KeyError, ValueError, AttributeError, TypeError, OSError, IndexError)


@dataclass(frozen=True)
class PptxContent:
    slides: tuple[Slide, ...]
    # Empty when the deck has no sections.
    sections: tuple[Section, ...]


def _shape_texts(shapes: Any) -> Iterator[str]:
    for shape in shapes:
        if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
            yield from _shape_texts(shape.shapes)
            continue
        if shape.has_text_frame:
            text = shape.text_frame.text.strip()
            if text:
                yield text
        if getattr(shape, "has_table", False) and shape.has_table:
            for row in shape.table.rows:
                for cell in row.cells:
                    text = cell.text.strip()
                    if text:
                        yield text


def _title(slide: Any) -> str | None:
    shape = slide.shapes.title
    if shape is None or not shape.has_text_frame:
        return None
    text = re.sub(r"\s+", " ", shape.text_frame.text).strip()[:MAX_TITLE_CHARS]
    return text or None


def _sections(presentation: Any, slide_ids: list[int]) -> tuple[Section, ...]:
    number_of = {slide_id: index + 1 for index, slide_id in enumerate(slide_ids)}
    found: list[Section] = []
    root = presentation.part._element
    for section in etree._Element.xpath(root, "//p14:section", namespaces=_NS):
        ids = etree._Element.xpath(section, "./p14:sldIdLst/p14:sldId/@id", namespaces=_NS)
        numbers = tuple(number_of[int(i)] for i in ids if int(i) in number_of)
        name = re.sub(r"\s+", " ", section.get("name") or "").strip()[:MAX_TITLE_CHARS]
        found.append(Section(name=name or f"Section {len(found) + 1}", slides=numbers))
    return tuple(found)


def read_pptx(data: bytes, limits: PptxLimits | None = None) -> PptxContent:
    """Slides of a PPTX and its sections. Raises PptxError with code too_large, zip_bomb,
    malformed, macros or too_many_slides."""
    limits = limits or PptxLimits()
    check_zip(data, limits.zip, "ppt/presentation.xml")
    try:
        presentation = Presentation(io.BytesIO(data))
        ids = [int(i) for i in presentation.part._element.xpath("//p:sldIdLst/p:sldId/@id")]
        if len(ids) > limits.max_slides:
            raise PptxError("too_many_slides")
        slides: list[Slide] = []
        chars = 0
        for number, slide in enumerate(presentation.slides, start=1):
            text = "\n".join(_shape_texts(slide.shapes))[: limits.max_chars_per_slide]
            chars += len(text)
            if chars > limits.max_chars:
                raise PptxError("too_many_slides")
            slides.append(Slide(number=number, title=_title(slide), text=text))
        sections = _sections(presentation, ids)
    except PptxError:
        raise
    except _LIBRARY_ERRORS as error:
        raise PptxError("malformed") from error
    return PptxContent(slides=tuple(slides), sections=sections)
