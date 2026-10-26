"""The one way into a PDF in ai-service (ADR-0011). Swapping the library changes only
`pdfium_impl.py`."""

from ai_service.pdf.pdfium_impl import PdfDocument, open_pdf
from ai_service.pdf.types import (
    MAX_TITLE_CHARS,
    MIN_TEXT_CHARS,
    OutlineEntry,
    PageText,
    PdfError,
    PdfErrorCode,
    PdfLimits,
    RenderedPage,
)

__all__ = [
    "MAX_TITLE_CHARS",
    "MIN_TEXT_CHARS",
    "OutlineEntry",
    "PageText",
    "PdfDocument",
    "PdfError",
    "PdfErrorCode",
    "PdfLimits",
    "RenderedPage",
    "open_pdf",
]
