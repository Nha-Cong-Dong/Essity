"""What pdf/ returns (ADR-0011). Frozen dataclasses, so results pickle across a process pipe."""

from dataclasses import dataclass
from typing import Literal

# A page with fewer non-space characters than this has no usable text layer: a scan, a
# picture-only slide, or a scan with a digital page number stamped on it (T4.7: read by vision).
MIN_TEXT_CHARS = 10
# Bookmark titles longer than this are cut; a real title is a line, not a page.
MAX_TITLE_CHARS = 500

PdfErrorCode = Literal[
    "too_large",
    "too_many_pages",
    "encrypted",
    "malformed",
    "deadline",
    "page_out_of_range",
    "closed",
]


class PdfError(Exception):
    """The file cannot be read as asked. `code` is stable and safe to store or log, and is
    the whole message: the library's text stays on `__cause__` and is lost when pickled."""

    def __init__(self, code: PdfErrorCode) -> None:
        super().__init__(code)
        self.code: PdfErrorCode = code

    def __reduce__(self) -> tuple[type["PdfError"], tuple[PdfErrorCode]]:
        return (PdfError, (self.code,))


@dataclass(frozen=True)
class PdfLimits:
    """Bounds for one file. Defaults suit a 300-page slide deck with room to spare."""

    max_bytes: int = 200 * 1024 * 1024
    max_pages: int = 2000
    # Long side of a rendered page. Callers pass less: ~1568 for vision, ~400 for thumbnails.
    max_render_px: int = 2000
    max_render_pixels: int = 4_000_000
    max_outline_entries: int = 5000
    max_outline_depth: int = 16
    max_text_chars_per_page: int = 200_000
    # Checked before each page is read; it cannot interrupt the C library inside one page.
    deadline_s: float = 120.0


@dataclass(frozen=True)
class OutlineEntry:
    title: str
    # 0 for a top-level bookmark.
    level: int
    # 0-based page in the file; None when the bookmark points nowhere usable.
    page_index: int | None


@dataclass(frozen=True)
class PageText:
    text: str
    # True when the page has no usable text layer and must be read from its image.
    needs_vision: bool


@dataclass(frozen=True)
class RenderedPage:
    png: bytes
    width: int
    height: int
