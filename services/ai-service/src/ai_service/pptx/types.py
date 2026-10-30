"""What pptx/ returns (ADR-0011, T7.3). Frozen dataclasses, like pdf/types.py."""

from dataclasses import dataclass

from ai_service.office_zip import OfficeError, ZipLimits

MAX_TITLE_CHARS = 500

PptxError = OfficeError


@dataclass(frozen=True)
class PptxLimits:
    zip: ZipLimits = ZipLimits()
    max_slides: int = 1000
    max_chars_per_slide: int = 100_000
    max_chars: int = 5_000_000


@dataclass(frozen=True)
class Slide:
    # 1-based position in the deck.
    number: int
    # The title placeholder's text; None when the slide has none.
    title: str | None
    # All text of the slide in shape-tree order; "" for a picture-only slide.
    text: str


@dataclass(frozen=True)
class Section:
    name: str
    # 1-based slide numbers in the section, in order.
    slides: tuple[int, ...]
