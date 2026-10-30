"""What docx/ returns (ADR-0011, T7.3). Frozen dataclasses, like pdf/types.py."""

from dataclasses import dataclass

from ai_service.office_zip import OfficeError, ZipLimits

# Bounds the title kept for a heading; a heading is a line, not a page.
MAX_TITLE_CHARS = 500
# Deepest heading level kept (Heading 1..9 in Word).
MAX_HEADING_LEVEL = 8

DocxError = OfficeError


@dataclass(frozen=True)
class DocxLimits:
    zip: ZipLimits = ZipLimits()
    max_paragraphs: int = 200_000
    max_chars: int = 5_000_000


@dataclass(frozen=True)
class Paragraph:
    text: str
    # 0 for a top-level heading; None for body text.
    heading_level: int | None
    # Title of the nearest heading at or above this paragraph; None before the first heading.
    anchor: str | None
